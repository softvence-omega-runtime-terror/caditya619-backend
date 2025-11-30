from tortoise import fields, models
import uuid
from tortoise.validators import MinValueValidator, MaxValueValidator


class RiderProfile(models.Model):
    id = fields.IntField(pk=True)
    user = fields.OneToOneField("models.User", related_name="rider_profile", on_delete=fields.CASCADE)
    driving_license = fields.CharField(max_length=100)
    nid = fields.CharField(max_length=60)
    profile_image = fields.CharField(max_length=255, null=True)
    national_id_document = fields.CharField(max_length=255, null=True)
    driving_license_document = fields.CharField(max_length=255, null=True)
    vehicle_registration_document = fields.CharField(max_length=255, null=True)
    vehicle_insurance_document = fields.CharField(max_length=255, null=True)
    current_balance = fields.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_available = fields.BooleanField(default=False)
    online_start_time = fields.DatetimeField(null=True, default=None)
    is_verified = fields.BooleanField(default=False)
    bank_account_number = fields.CharField(max_length=20, null=True, blank=True)
    bank_ifsc = fields.CharField(max_length=11, null=True, blank=True)
    bank_holder_name = fields.CharField(max_length=100, null=True, blank=True)
    is_bank_verified = fields.BooleanField(default=False)
    fcm_token = fields.CharField(max_length=255, null=True, blank=True)
    referral_code = fields.CharField(max_length=20, unique=True, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "rider_profiles"

    def __str__(self):
        return f"RiderProfile of User ID {self.user_id}"
    




class Vehicle(models.Model):
    vehicle_type_choices = [
        ("car", "Car"),
        ("bike", "Bike"),
        ("truck", "Truck"),
        ("van", "Van")
    ]
    id = fields.IntField(pk=True)
    rider_profile = fields.ForeignKeyField("models.RiderProfile", on_delete=fields.CASCADE, related_name="vehicles")
    vehicle_type = fields.CharField(max_length=30, choices=vehicle_type_choices)
    model = fields.CharField(max_length=50)
    license_plate_number = fields.CharField(max_length=20, unique=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "vehicles"

    def __str__(self):
        return f"{self.model} ({self.license_plate_number})"
    


class Zone(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
    description = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "zones"

    def __str__(self):
        return self.name
    


class RiderZoneAssignment(models.Model):
    id = fields.IntField(pk=True)
    rider_profile = fields.ForeignKeyField("models.RiderProfile", on_delete=fields.CASCADE, related_name="zone_assignments")
    zone = fields.ForeignKeyField("models.Zone", on_delete=fields.CASCADE, related_name="rider_assignments")
    assigned_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "rider_zone_assignments"
        unique_together = ("rider_profile", "zone")

    def __str__(self):
        return f"RiderProfile ID {self.rider_profile_id} assigned to Zone {self.zone_id}"





class RiderCurrentLocation(models.Model):
    id = fields.IntField(pk=True)
    rider_profile = fields.OneToOneField("models.RiderProfile", on_delete=fields.CASCADE, related_name="current_location")
    latitude = fields.FloatField(default= 0.0)
    longitude = fields.FloatField(default= 0.0)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "rider_current_locations"

    def __str__(self):
        return f"Location of RiderProfile ID {self.rider_profile_id}: ({self.latitude}, {self.longitude})"    
    



class RiderAvailabilityStatus(models.Model):
    id = fields.IntField(pk=True)
    rider_profile = fields.OneToOneField("models.RiderProfile", on_delete=fields.CASCADE, related_name="availability_status")
    is_available = fields.BooleanField(default=False)
    strat_at = fields.TimeField(null=True)
    end_at = fields.TimeField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "rider_availability_statuses"

    def __str__(self):
        return f"Availability of RiderProfile ID {self.rider_profile_id}: {'Available' if self.is_available else 'Unavailable'}"








#*********************************************************************#
#              Rider Order and Delivery Models
#*********************************************************************#

class OrderOffer(models.Model):
    """
    Records that order was offered to rider and result (accepted/rejected/timeout).
    """
    id = fields.IntField(pk=True)
    order = fields.ForeignKeyField("models.Order", related_name="offers", on_delete=fields.CASCADE)
    rider = fields.ForeignKeyField("models.RiderProfile", related_name="order_offers", on_delete=fields.CASCADE)
    customer_lat = fields.FloatField()
    customer_lng = fields.FloatField()
    vendor_lat = fields.FloatField()
    vendor_lng = fields.FloatField()
    offered_at = fields.DatetimeField(auto_now_add=True)
    responded_at = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=20, default="offered")  # offered/accepted/rejected/timeout
    reason = fields.TextField(null=True)
    pickup_distance_km = fields.FloatField()
    pickup_time = fields.DatetimeField()
    eta_minutes = fields.IntField()
    base_rate = fields.DecimalField(max_digits=10, decimal_places=2, default=44.00)
    distance_bonus = fields.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    offered_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField()
    accepted_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    is_on_time = fields.BooleanField(null=True)
    is_combined = fields.BooleanField(default=False)
    combined_pickups = fields.JSONField(null=True)  # list of dicts: [{"name": "Thai Spice", "amount": 44}]

    class Meta:
        table = "order_offers"
        indexes = [("order_id","rider_id")]








#*********************************************************************#
#              Rider State Related Models
#*********************************************************************#



# class Rating(models.Model):
#     id = fields.UUIDField(pk=True, default=uuid.uuid4)
#     order = fields.ForeignKeyField("models.Order", related_name="ratings")
#     score = fields.FloatField()
#     created_at = fields.DatetimeField(auto_now_add=True)

#     class Meta:
#         table = "ratings"

class Complaint(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    user = fields.ForeignKeyField("models.User", related_name="complaints", null=True)
    rider = fields.ForeignKeyField("models.RiderProfile", related_name="complaints", null=True)
    description = fields.TextField()
    is_serious = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "complaints"

class WorkDay(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    rider = fields.ForeignKeyField("models.RiderProfile", related_name="work_days")
    date = fields.DateField()
    hours_worked = fields.FloatField(default=0.0)
    order_offer_count = fields.IntField(default=0)
    is_scheduled_leave = fields.BooleanField(default=False)

    class Meta:
        table = "work_days"
        unique_together = (("rider", "date"),)

class Notification(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    rider = fields.ForeignKeyField("models.RiderProfile", related_name="notifications")
    message = fields.TextField()
    type = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    is_read = fields.BooleanField(default=False)

    class Meta:
        table = "notifications"

class Withdrawal(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    rider = fields.ForeignKeyField("models.RiderProfile", related_name="withdrawals")
    amount = fields.DecimalField(max_digits=10, decimal_places=2)
    status = fields.CharField(max_length=50, default="pending")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "withdrawals"



class HelpAndSupport(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    rider = fields.ForeignKeyField("models.RiderProfile", related_name="help_support_requests")
    subject = fields.CharField(max_length=255)
    description = fields.TextField(max_length=2000)
    attachment = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    resolved_at = fields.DatetimeField(null=True)

    class Meta:
        table = "help_and_support"


#*********************************************************************#
#              End of Rider State Related Models
#*********************************************************************#



class DeviceToken(models.Model):
    id = fields.IntField(pk=True)
    user_id = fields.IntField()
    token = fields.CharField(max_length=256)
    platform = fields.CharField(max_length=32)
    created_at = fields.DatetimeField(auto_now_add=True)




#*********************************************************************#
#              Training Section Models
#*********************************************************************#


# class TrainingVideo(models.Model):
#     id = fields.IntField(pk=True)
#     title = fields.CharField(max_length=100)
#     duration = fields.CharField(max_length=10, default="0:00")
#     video_file = fields.CharField(max_length=500)  # e.g., "/media/training/get_started.mp4"
#     thumbnail = fields.CharField(max_length=500, null=True, blank=True)
#     order = fields.IntField(default=0)
#     uploaded_at = fields.DatetimeField(auto_now_add=True)

#     class Meta:
#         table = "training_videos"
#         ordering = ["order"]


# class TrainingPDF(models.Model):
#     id = fields.IntField(pk=True)
#     title = fields.CharField(max_length=100)
#     file = fields.CharField(max_length=500)  # e.g., "/media/pdfs/handbook.pdf"
#     icon = fields.CharField(max_length=50, default="document")
#     uploaded_at = fields.DatetimeField(auto_now_add=True)

#     class Meta:
#         table = "training_pdfs"



class QuizQuestion(models.Model):
    id = fields.IntField(pk=True)
    question = fields.TextField()
    option_a = fields.CharField(max_length=200)
    option_b = fields.CharField(max_length=200)
    option_c = fields.CharField(max_length=200)
    option_d = fields.CharField(max_length=200, null=True, blank=True)
    correct_answer = fields.CharField(max_length=1)  # "A", "B", "C", "D"
    explanation = fields.TextField(null=True, blank=True)

    class Meta:
        table = "quiz_questions"


class RiderQuizAttempt(models.Model):
    id = fields.IntField(pk=True)
    rider = fields.ForeignKeyField("models.RiderProfile", related_name="quiz_attempts")
    score = fields.IntField()  # out of 100
    correct_answers = fields.IntField()
    total_questions = fields.IntField(default=5)
    passed = fields.BooleanField(default=False)
    attempted_at = fields.DatetimeField(auto_now_add=True)
    is_latest = fields.BooleanField(default=True)

    class Meta:
        table = "rider_quiz_attempts"




class TrainingVideo(models.Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=200)
    duration = fields.CharField(max_length=10, null=True)  # optional
    video_file = fields.CharField(max_length=500)  # /static/videos/xyz.mp4
    thumbnail = fields.CharField(max_length=500, null=True)
    order = fields.IntField(default=0)
    is_active = fields.BooleanField(default=True)

class TrainingPDF(models.Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=200)
    file = fields.CharField(max_length=500)  # /static/pdfs/xyz.pdf
    order = fields.IntField(default=0)
    is_active = fields.BooleanField(default=True)





class Referral(models.Model):
    id = fields.IntField(pk=True)
    referrer = fields.ForeignKeyField("models.RiderProfile", related_name="referrals_made")
    referred = fields.ForeignKeyField("models.RiderProfile", related_name="referred_by", null=True)
    code_used = fields.CharField(max_length=20)
    status = fields.CharField(max_length=10, default="pending")  # pending / active
    earned = fields.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    created_at = fields.DatetimeField(auto_now_add=True)




#*********************************************************************#
#              fees and bonuses Models
#*********************************************************************#


class RiderFeesAndBonuses(models.Model):
    id = fields.IntField(pk=True)
    rider_base_salary = fields.DecimalField(max_digits=10, decimal_places=2, default=8000.00)
    rider_delivery_fee = fields.DecimalField(max_digits=10, decimal_places=2, default=44.00)
    distance_bonus_per_km = fields.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    weekly_bonus = fields.DecimalField(max_digits=10, decimal_places=2, default=400.00)
    referral_bonus = fields.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    excellence_bonus = fields.DecimalField(max_digits=10, decimal_places=2, default=2000.00)
    updated_at = fields.DatetimeField(auto_now=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "rider_fees_and_bonuses"



class RiderReview(models.Model):
    id = fields.IntField(pk=True)
    rider = fields.ForeignKeyField("models.RiderProfile", related_name="rider", on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', on_delete=fields.CASCADE, related_name='rider_reviews') 
    rating = fields.IntField(validators=[MinValueValidator(1), MaxValueValidator(5)], null=True)
    comment = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)