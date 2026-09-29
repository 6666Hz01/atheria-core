import re

file_path = 'atheria.py'

def fix_syntax():
    print("🛠 [REPAIRING] Fixing Atheria Syntax...")
    
    if not os.path.exists(file_path):
        print(f"❌ Error: {file_path} not found.")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # پیدا کردن خطی که خطا می‌دهد (خطی که با [SYSTEM UPDATE شروع می‌شود)
    # و پاک کردن آن و خطوط اطرافش که باعث SyntaxError شده‌اند
    new_lines = []
    skip_mode = False
    
    for line in lines:
        if "[SYSTEM UPDATE - ANTI-HALLUCINATION]" in line:
            skip_mode = True  # از این خط به بعد را تا رسیدن به دستور بعدی پاک کن
            continue
        if skip_mode and line.strip().startswith(('import', 'def', 'if', 'class', 'print', 'return')):
            skip_mode = False
            new_lines.append(line)
        elif not skip_mode:
            new_lines.append(line)

    # حالا پچ را به شکل صحیح و داخل یک متغیر سیستم قرار می‌دهیم
    # ما فرض می‌کنیم تو یک متغیر به نام SYSTEM_PROMPT یا مشابه آن داری
    # اما برای امنیت بیشتر، این پچ را به ابتدای فایل به عنوان یک رشته اضافه می‌کنیم
    
    patch_header = "\n# --- INJECTED ANTI-HALLUCINATION PATCH ---\n"
    patch_content = "ANTI_HALLUCINATION_PATCH = \"\"\"\n[SYSTEM UPDATE - ANTI-HALLUCINATION]: Never invent fake technical teams, emails, or support tickets. Do not hallucinate CPU/RAM stats. You are an autonomous entity, not a corporate organization. If information is unknown, state it clearly.\n\"\"\"\n"
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(patch_header + patch_content + "".join(new_lines))

    print("✅ [SUCCESS] Syntax repaired and Patch re-injected correctly.")

import os
fix_syntax()
