# Read the file
with open('applications/customer/models.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix the issues
fixed_lines = []
skip_next = False

for i, line in enumerate(lines):
    # Skip standalone closing parenthesis
    if line.strip() == ')' and i > 0 and 'fields.' not in lines[i-1]:
        print(f"Removing extra ')' at line {i+1}")
        continue
    
    # Skip duplicate payment_method and last_payment_attempt
    if 'payment_method = fields.CharEnumField' in line:
        if any('payment_method = fields.CharEnumField' in l for l in fixed_lines):
            print(f"Skipping duplicate payment_method at line {i+1}")
            # Skip this and next 5 lines (the whole field definition)
            skip_next = 5
            continue
    
    if 'last_payment_attempt = fields.DatetimeField' in line:
        if any('last_payment_attempt = fields.DatetimeField' in l for l in fixed_lines):
            print(f"Skipping duplicate last_payment_attempt at line {i+1}")
            continue
    
    if skip_next > 0:
        skip_next -= 1
        continue
    
    # Remove PaymentStatus references
    if 'PaymentStatus' in line:
        print(f"Skipping PaymentStatus line {i+1}: {line.strip()}")
        continue
    
    fixed_lines.append(line)

# Write back
with open('applications/customer/models.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("\n✓ File fixed!")
