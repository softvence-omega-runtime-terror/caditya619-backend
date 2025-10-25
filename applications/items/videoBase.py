from tortoise import models, fields

class VideoBase(models.Model):
    VIDEO_TYPE_CHOICES = ["youtube", "cloudinary", "basic"]
    
    type = fields.CharField(
        max_length=20,
        choices=VIDEO_TYPE_CHOICES,
        default="youtube",
        description="Select the type of video source"
    )
    video_id = fields.CharField(max_length=400, description="YouTube video ID or Cloudinary video ID")
    title = fields.TextField(max_length=200, null=True, description="Title of the video")
    description = fields.TextField(max_length=1500, null=True, description="Description of the video")
    autoplay = fields.CharField(
        max_length=20,
        default="false",
        description="Autoplay mode: false, true, on-scroll"
    )
    muted = fields.BooleanField(default=True)
    controls = fields.BooleanField(default=True)
    loop = fields.BooleanField(default=False)
    playlist = fields.BooleanField(default=False)
    endScreen = fields.BooleanField(default=True)
    pip = fields.BooleanField(default=False, description="Picture in Picture Mode")
    poster = fields.CharField(max_length=200, null=True, default=None, description="Poster image path")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self):
        return f"({self.type}) - {self.video_id}"
