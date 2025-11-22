# utils/vendor_rating_calculator.py
"""
Utility to automatically update vendor ratings based on customer reviews
This should be called whenever a customer creates/updates/deletes a review
"""

from typing import Optional
from tortoise.functions import Avg, Count
from applications.user.vendor import VendorProfile


class VendorRatingCalculator:
    """Calculate and update vendor ratings based on customer reviews"""
    
    @staticmethod
    async def update_vendor_rating(vendor_id: int) -> Optional[VendorProfile]:
        """
        Update vendor's rating based on all customer reviews
        This is called automatically when customers add/update/delete reviews
        
        Args:
            vendor_id: The vendor's user ID
            
        Returns:
            Updated VendorProfile or None if vendor not found
        """
        from applications.restaurants.models import VendorReview
        
        # Get vendor profile
        vendor_profile = await VendorProfile.get_or_none(user_id=vendor_id)
        if not vendor_profile:
            return None
        
        # Calculate average rating from customer reviews
        result = await VendorReview.filter(vendor_id=vendor_id).aggregate(
            avg_rating=Avg("rating"),
            review_count=Count("id")
        )
        
        # Update vendor profile
        avg_rating = result.get("avg_rating") or 0.0
        review_count = result.get("review_count") or 0
        
        vendor_profile.rating = round(avg_rating, 2)
        vendor_profile.review_count = review_count
        
        # Auto-set top_rated if rating is high and has enough reviews
        if avg_rating >= 4.5 and review_count >= 10:
            vendor_profile.is_top_rated = True
        elif avg_rating < 4.0 or review_count < 5:
            vendor_profile.is_top_rated = False
        
        await vendor_profile.save(update_fields=["rating", "review_count", "is_top_rated"])
        
        # Also update popularity score
        await VendorRatingCalculator.calculate_popularity(vendor_id)
        
        return vendor_profile
    
    @staticmethod
    async def calculate_popularity(vendor_id: int) -> Optional[float]:
        """
        Calculate vendor popularity score based on:
        - Average rating (40% weight)
        - Number of reviews (30% weight)
        - Total sales/orders (30% weight)
        
        Returns popularity score between 0-5
        """
        from applications.user.vendor import VendorProfile
        from applications.items.models import Item
        
        vendor_profile = await VendorProfile.get_or_none(user_id=vendor_id)
        if not vendor_profile:
            return None
        
        # Get total sales from vendor's items
        items_stats = await Item.filter(vendor_id=vendor_id).aggregate(
            total_sales=Count("total_sale")
        )
        total_sales = items_stats.get("total_sales") or 0
        
        # Calculate weighted popularity score (0-5 scale)
        rating_score = vendor_profile.rating * 0.4  # Max 2.0
        review_score = min((vendor_profile.review_count / 100), 5) * 0.3  # Max 1.5
        sales_score = min((total_sales / 1000), 5) * 0.3  # Max 1.5
        
        popularity = round(rating_score + review_score + sales_score, 2)
        
        vendor_profile.popularity = min(popularity, 5.0)  # Cap at 5.0
        await vendor_profile.save(update_fields=["popularity"])
        
        return vendor_profile.popularity
    
    @staticmethod
    async def recalculate_all_vendors():
        """
        Recalculate ratings for all food vendors
        Useful for maintenance or after data migration
        """
        vendors = await VendorProfile.filter(type="food").all()
        
        updated_count = 0
        for vendor in vendors:
            result = await VendorRatingCalculator.update_vendor_rating(vendor.user_id)
            if result:
                updated_count += 1
        
        return {
            "total_vendors": len(vendors),
            "updated_count": updated_count
        }


# Management command to recalculate all ratings
async def recalculate_all_vendor_ratings():
    """
    Run this script to recalculate all vendor ratings
    
    Usage:
        python -m scripts.recalculate_ratings
    """
    from tortoise import Tortoise
    
    await Tortoise.init(
        db_url='postgres://user:password@localhost:5432/your_database',
        modules={'models': ['applications.items.models', 'applications.user.vendor', 'applications.restaurants.models']}
    )
    
    print("Recalculating vendor ratings...")
    result = await VendorRatingCalculator.recalculate_all_vendors()
    
    print(f"✅ Updated {result['updated_count']}/{result['total_vendors']} vendors")
    
    await Tortoise.close_connections()


if __name__ == "__main__":
    import asyncio
    asyncio.run(recalculate_all_vendor_ratings())