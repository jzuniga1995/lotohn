#!/usr/bin/env python3
"""
Wrapper para ejecutar scraper y actualizar GitHub
"""
import os
import subprocess
import json
from datetime import datetime
import sys

def run_command(cmd, description=""):
    """Ejecuta comando y retorna resultado"""
    print(f"🔄 {description}")
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print(f"✅ {description} - OK")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print(f"❌ {description} - ERROR")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("=" * 60)
    print("🎯 SCRAPER LOTO HONDURAS - RENDER")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. Ejecutar scraper
    print("\n1️⃣ EJECUTANDO SCRAPER...")
    if not run_command("python loto_scraper.py", "Scraper"):
        print("❌ Scraper falló")
        sys.exit(1)
    
    # 2. Verificar si hay archivo de resultados
    if not os.path.exists('resultados_hoy.json'):
        print("⚠️ No se generó resultados_hoy.json")
        sys.exit(1)
    
    # 3. Configurar Git
    print("\n2️⃣ CONFIGURANDO GIT...")
    github_token = os.getenv('GITHUB_TOKEN')
    github_repo = os.getenv('GITHUB_REPO', 'jzuniga1995/lotohn')
    
    if not github_token:
        print("❌ GITHUB_TOKEN no configurado")
        sys.exit(1)
    
    # Configurar remote con token
    remote_url = f"https://{github_token}@github.com/{github_repo}.git"
    
    run_command("git config --global user.email 'render-bot@lotohn.com'", "Config email")
    run_command("git config --global user.name 'Render Bot'", "Config name")
    run_command(f"git remote set-url origin {remote_url}", "Config remote")
    
    # 4. Verificar cambios
    print("\n3️⃣ VERIFICANDO CAMBIOS...")
    run_command("git add resultados_hoy.json", "Staging cambios")
    
    # Verificar si hay diferencias
    result = subprocess.run(
        "git diff --staged --quiet",
        shell=True
    )
    
    if result.returncode == 0:
        print("ℹ️ No hay cambios nuevos")
        print("✅ Proceso completado sin actualizaciones")
        return
    
    # 5. Commit y Push
    print("\n4️⃣ ACTUALIZANDO GITHUB...")
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if run_command(f'git commit -m "🎯 Actualizar resultados - {timestamp}"', "Commit"):
        if run_command("git push origin main", "Push a GitHub"):
            print("\n" + "=" * 60)
            print("✅ PROCESO COMPLETADO EXITOSAMENTE")
            print("=" * 60)
        else:
            print("❌ Error al hacer push")
            sys.exit(1)
    else:
        print("❌ Error al hacer commit")
        sys.exit(1)

if __name__ == "__main__":
    main()