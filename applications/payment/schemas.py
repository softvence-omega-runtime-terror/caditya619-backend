# applications/payment/schemas.py

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime

# ✅ Only import enums, NOT model classes
from applications.payment.models import PaymentStatus, PaymentProvider

# Rest of your schemas...
# (Keep all the schema definitions from the previous artifact)
