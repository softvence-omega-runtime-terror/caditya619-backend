from tortoise import fields, models

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
    is_available = fields.BooleanField(default=False)
    is_verified = fields.BooleanField(default=False)
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
#              Rider State Related Models
#*********************************************************************#


class RiderDailyStats(models.Model):
    id = fields.IntField(pk=True)
    rider_profile = fields.ForeignKeyField("models.RiderProfile", on_delete=fields.CASCADE, related_name="daily_stats")
    date = fields.DateField()
    delivery_count = fields.IntField(default=0)



