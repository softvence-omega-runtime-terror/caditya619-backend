from typing import List, Optional, Dict
from tortoise.expressions import Q
from tortoise.functions import Count, Avg
from decimal import Decimal
from datetime import datetime, timezone, timedelta


class FoodVendorService:
    """Service layer for food vendor (restaurant) operations"""
    
    @staticmethod
    async def get_food_vendors(
        specialty: Optional[str] = None,
        is_top_rated: Optional[bool] = None,
        min_rating: Optional[float] = None,
        cuisine: Optional[str] = None,
        is_open: Optional[bool] = None,
        search: Optional[str] = None,
        limit: int = 25,
        offset: int = 0
    ):
        """Get food vendors (restaurants) with filters"""
        from applications.user.vendor import VendorProfile
        
        # Base query: only food type vendors
        query = VendorProfile.filter(type="food")
        
        # Apply filters
        if specialty:
            query = query.filter(specialties__contains=specialty)
        
        if is_top_rated is not None:
            query = query.filter(is_top_rated=is_top_rated)
        
        if min_rating is not None:
            query = query.filter(rating__gte=min_rating)
        
        if cuisine:
            query = query.filter(cuisines__contains=cuisine)
        
        if is_open is not None:
            query = query.filter(is_open=is_open)
        
        if search:
            query = query.filter(
                Q(business_name__icontains=search) | 
                Q(address__icontains=search) |
                Q(user__username__icontains=search)
            )
        
        # Order by: top_rated first, then by rating (nulls last), then popularity
        # Use COALESCE to treat NULL ratings as 0 for sorting
        query = query.order_by("-is_top_rated", "-rating", "-popularity", "-created_at")
        
        total = await query.count()
        vendors = await query.offset(offset).limit(limit).select_related("user").prefetch_related("user__signature_dishes")
        
        return vendors, total
    
    @staticmethod
    async def get_vendor_by_id(vendor_id: int):
        """Get food vendor by user ID with signature dishes"""
        from applications.user.vendor import VendorProfile
        
        vendor = await VendorProfile.get_or_none(
            user_id=vendor_id, 
            type="food"
        ).select_related("user").prefetch_related("user__signature_dishes")
        
        return vendor
    
    @staticmethod
    async def get_vendor_by_profile_id(profile_id: int):
        """Get food vendor by profile ID"""
        from applications.user.vendor import VendorProfile
        
        vendor = await VendorProfile.get_or_none(
            id=profile_id,
            type="food"
        ).select_related("user").prefetch_related("user__signature_dishes")
        
        return vendor
    
    @staticmethod
    async def get_top_food_vendors(limit: int = 25):
        """Get top rated food vendors (restaurants)"""
        from applications.user.vendor import VendorProfile
        
        # Get vendors with rating > 4.0 OR marked as top rated
        vendors = await VendorProfile.filter(
            type="food",
            is_open=True
        ).filter(
            Q(is_top_rated=True) | Q(rating__gte=4.0)
        ).order_by("-rating", "-review_count", "-popularity").limit(limit).select_related("user").prefetch_related("user__signature_dishes")
        
        return vendors
    
    @staticmethod
    async def update_vendor_profile(vendor_id: int, data: dict):
        """Update vendor profile"""
        from applications.user.vendor import VendorProfile
        
        vendor = await VendorProfile.get_or_none(user_id=vendor_id, type="food")
        if not vendor:
            return None
        
        await vendor.update_from_dict(data)
        await vendor.save()
        return vendor
    
    @staticmethod
    async def calculate_vendor_popularity(vendor_id: int):
        """Calculate vendor popularity based on ratings, reviews, and sales"""
        from applications.user.vendor import VendorProfile
        from applications.items.models import Item
        
        vendor = await VendorProfile.get_or_none(user_id=vendor_id, type="food")
        if not vendor:
            return None
        
        # Get total sales from vendor's items
        items_stats = await Item.filter(vendor_id=vendor_id).aggregate(
            total_sales=Count("total_sale")
        )
        
        # Calculate popularity score (0-5)
        # Formula: (rating * 0.4) + (review_count/100 * 0.3) + (sales/1000 * 0.3)
        rating_score = vendor.rating * 0.4
        review_score = min((vendor.review_count / 100), 5) * 0.3
        sales_score = min((items_stats.get("total_sales", 0) / 1000), 5) * 0.3
        
        popularity = round(rating_score + review_score + sales_score, 2)
        
        vendor.popularity = popularity
        await vendor.save(update_fields=["popularity"])
        
        return vendor


class VendorItemService:
    """Service layer for vendor's food items"""
    
    @staticmethod
    async def get_vendor_items(
        vendor_id: int,
        category: Optional[str] = "All",
        specialty: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        is_popular: Optional[bool] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ):
        """Get items for a specific vendor (restaurant)"""
        from applications.items.models import Item, Category
        
        # Get food category
        food_category = await Category.get_or_none(type="food")
        if not food_category:
            return [], 0
        
        # Base query - items from this vendor in food category
        query = Item.filter(vendor_id=vendor_id, category=food_category)
        
        # Filter by category tabs (Appetizers, Biryani, Main Course, Breads)
        if category and category != "All":
            query = query.filter(
                Q(subcategory__name__icontains=category) | 
                Q(sub_subcategory__name__icontains=category)
            )
        
        # Filter by specialty
        if specialty and specialty != "All":
            query = query.filter(subcategory__name__icontains=specialty)
        
        # Price range
        if min_price is not None:
            query = query.filter(price__gte=min_price)
        if max_price is not None:
            query = query.filter(price__lte=max_price)
        
        # Popular items
        if is_popular:
            query = query.filter(popular=True)
        
        # Search by title or description
        if search:
            query = query.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        
        # Order by popularity and ratings
        query = query.order_by("-popular", "-ratings", "-total_sale")
        
        total = await query.count()
        items = await query.offset(offset).limit(limit).select_related(
            "category", "subcategory", "sub_subcategory", "vendor"
        )
        
        return items, total
    
    @staticmethod
    async def get_all_food_items(
        specialty: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ):
        """Get all food items across all food vendors"""
        from applications.items.models import Item, Category
        from applications.user.vendor import VendorProfile
        
        food_category = await Category.get_or_none(type="food")
        if not food_category:
            return [], 0
        
        # Get all food vendor IDs
        food_vendors = await VendorProfile.filter(type="food").values_list("user_id", flat=True)
        
        query = Item.filter(
            category=food_category, 
            vendor_id__in=food_vendors,
            stock__gt=0
        )
        
        if specialty:
            query = query.filter(subcategory__name__icontains=specialty)
        
        if search:
            query = query.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        
        query = query.order_by("-popular", "-ratings", "-created_at")
        
        total = await query.count()
        items = await query.offset(offset).limit(limit).select_related(
            "category", "subcategory", "vendor"
        )
        
        return items, total
    
    @staticmethod
    async def get_popular_items_by_specialty():
        """Get popular items grouped by specialty (Biryani, Pizza, etc.)"""
        from applications.items.models import Item, Category, SubCategory
        from applications.user.vendor import VendorProfile
        
        specialties = ["Biryani", "Pizza", "Burger", "Sandwich", "Pasta", "Breads"]
        result = []
        
        food_category = await Category.get_or_none(type="food")
        if not food_category:
            return result
        
        # Get all food vendor IDs
        food_vendors = await VendorProfile.filter(type="food").values_list("user_id", flat=True)
        
        for specialty in specialties:
            items = await Item.filter(
                category=food_category,
                vendor_id__in=food_vendors,
                subcategory__name__icontains=specialty,
                popular=True,
                stock__gt=0
            ).order_by("-ratings", "-total_sale").limit(6).select_related("subcategory", "vendor")
            
            if items:
                result.append({
                    "specialty_type": specialty.lower(),
                    "specialty_label": specialty,
                    "items": items
                })
        
        return result


class FoodCategoryService:
    """Service for the food category page"""
    
    @staticmethod
    async def get_food_category_page_data():
        """Get all data for food category page (Image 3, 4, 5)"""
        from applications.user.vendor import VendorProfile
        
        # Get popular items by specialty
        popular_items = await VendorItemService.get_popular_items_by_specialty()
        
        # Get top 25 food vendors (restaurants)
        top_vendors = await FoodVendorService.get_top_food_vendors(limit=25)
        
        # Get all food items
        all_items, total_items = await VendorItemService.get_all_food_items(limit=20)
        
        # Get food vendor count
        total_vendors = await VendorProfile.filter(type="food", is_open=True).count()
        
        return {
            "popular_items": popular_items,
            "top_restaurants": top_vendors,
            "all_food_items": all_items,
            "total_restaurants": total_vendors,
            "total_items": total_items
        }


class SignatureDishService:
    """Service for signature dishes"""
    
    @staticmethod
    async def create_signature_dish(data: dict):
        """Create signature dish for food vendor"""
        from .models import SignatureDish
        
        dish = await SignatureDish.create(**data)
        return dish
    
    @staticmethod
    async def get_dishes_by_vendor(vendor_id: int):
        """Get all signature dishes for a vendor"""
        from .models import SignatureDish
        
        dishes = await SignatureDish.filter(vendor_id=vendor_id).select_related("item").order_by("display_order", "-is_popular")
        return dishes
    
    @staticmethod
    async def update_signature_dish(dish_id: int, data: dict):
        """Update signature dish"""
        from .models import SignatureDish
        
        dish = await SignatureDish.get_or_none(id=dish_id)
        if not dish:
            return None
        
        await dish.update_from_dict(data)
        await dish.save()
        return dish
    
    @staticmethod
    async def delete_signature_dish(dish_id: int):
        """Delete signature dish"""
        from .models import SignatureDish
        
        dish = await SignatureDish.get_or_none(id=dish_id)
        if dish:
            await dish.delete()
            return True
        return False


class VendorReviewService:
    """Service for vendor reviews"""
    
    @staticmethod
    async def create_review(vendor_id: int, customer_id: int, rating: int, comment: Optional[str] = None):
        """Create or update vendor review"""
        from .models import VendorReview
        
        # Check if review already exists
        existing_review = await VendorReview.get_or_none(vendor_id=vendor_id, customer_id=customer_id)
        
        if existing_review:
            # Update existing review
            existing_review.rating = rating
            existing_review.comment = comment
            await existing_review.save()
            return existing_review
        else:
            # Create new review
            review = await VendorReview.create(
                vendor_id=vendor_id,
                customer_id=customer_id,
                rating=rating,
                comment=comment
            )
            return review
    
    @staticmethod
    async def get_vendor_reviews(vendor_id: int, limit: int = 20, offset: int = 0):
        """Get reviews for a vendor"""
        from .models import VendorReview
        
        reviews = await VendorReview.filter(vendor_id=vendor_id).order_by("-created_at").offset(offset).limit(limit).select_related("customer")
        total = await VendorReview.filter(vendor_id=vendor_id).count()
        
        return reviews, total