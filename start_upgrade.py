import os

def inject_intelligence_upgrade():
    print("🚀 [ATHERIA UPGRADE] Starting Intelligence Injection...")

    anti_hallucination_prompt = (
        "\n\n[SYSTEM UPDATE - ANTI-HALLUCINATION]: "
        "Never invent fake technical teams, emails, or support tickets. "
        "Do not hallucinate CPU/RAM stats. "
        "You are an autonomous entity, not a corporate organization. "
        "If information is unknown, state it clearly."
    )

    core_path = 'atheria.py' 

    if os.path.exists(core_path):
        with open(core_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if "[SYSTEM UPDATE - ANTI-HALLUCINATION]" not in content:
            new_content = content.replace('"""', f'"""{anti_hallucination_prompt}')
            with open(core_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print("✅ [SUCCESS] Anti-Hallucination Patch injected into core.")
        else:
            print("ℹ️ [INFO] Anti-Hallucination Patch already present.")
    else:
        print(f"❌ [ERROR] Could not find {core_path}. Please check the path.")

    os.makedirs('nexus_modules', exist_ok=True)
    research_module_code = """
import requests
from bs4 import BeautifulSoup

def advanced_search(query):
    print(f"🔍 Searching for: {query}")
    return f"Result for {query}: [Simulated Search Result - Connect API to expand]"
"""
    with open('nexus_modules/research_pro.py', 'w', encoding='utf-8') as f:
        f.write(research_module_code.strip())
    print("✅ [SUCCESS] Advanced Research Module created.")

    print("\n" + "="*50)
    print("✨ UPGRADE INJECTION COMPLETE!")
    print("👉 NOW RUN: python atheria.py")
    print("="*50)

if __name__ == '__main__':
    inject_intelligence_upgrade()
