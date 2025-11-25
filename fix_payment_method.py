with open('applications/customer/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the payment_method field - remove default
content = content.replace(
    '''payment_method = fields.CharEnumField(
        PaymentMethodType,
        max_length=20,
        default=PaymentMethodType.PENDING,
        null=True
    )''',
    '''payment_method = fields.CharEnumField(
        PaymentMethodType,
        max_length=20,
        null=True
    )'''
)

with open('applications/customer/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Payment method field fixed!")
