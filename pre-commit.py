import os
import re
import subprocess

VERSION_PATTERN = r"'version': '(\d+\.\d+)\.(\d+)\.(\d+)\.(\d+)'"

def get_repo_root():
    try:
        return subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).decode('utf-8').strip() 
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while retrieving repo root: {e}")
        return None

def get_working_dir():
    try:
        return os.getcwd()
    except OSError as e:
        print(f"Error occurred while retrieving working directory: {e}")
        return None

def get_addons_changed(working_dir):
    try:
        lines = subprocess.check_output(["git", "diff", "--numstat","HEAD"]).decode("utf-8").split('\n')

        file_changes = {}
        for line in lines:
            add,rem, file_path = line.split("\t")
            if (file_path.endswith('.py') or file_path.endswith('.xml') or file_path.endswith('.csv') or file_path.endswith('.po')):
                changed_amount = add + rem
                addon_name = file_path[0]
                if addon_name in file_changes:
                    file_changes[addon_name] += changed_amount
                else:
                    file_changes[addon_name] = changed_amount

        return file_changes
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while retrieving changed files: {e}")
        return {}

def manifest_increase(change_amount, old_version):
    try:
        odoo_main_vers, odoo_vers, x,y,z = old_version.split(".")

        if change_amount <50:
            z = str(int(z)+1)
        elif change_amount <100:
            y = str(int(y)+1)
        elif change_amount >100:
            x = str(int(x)+1)
        
        return '.'.join([odoo_main_vers,odoo_vers,x,y,z])
    except ValueError as e:
        print(f"Error occurred while incrementing version: {e}")
        return None

def get_manifest_content(branch_name, addon_name):
    try:
        man_content = subprocess.check_output(['git', 'show', f'{branch_name}:{addon_name}/__manifest__.py']).decode("utf-8")
        return man_content
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while retrieving manifest content: {e}")
        return None

def get_manifest_version(content):
    try:
        match = re.search(VERSION_PATTERN, content)
        if match:
            return '.'.join(match.group(1, 2, 3, 4))
        return None
    except re.error as e:
        print(f"Error occurred while parsing version from manifest content: {e}")
        return None

def update_manifest(addon_dir, new_version):
    try:
        manifest_path = os.path.join(addon_dir, '__manifest__.py')
        with open(manifest_path, 'r') as f:
            content = f.read()

        updated_content = re.sub(VERSION_PATTERN, f"'version': '{new_version}'", content)

        with open(manifest_path, 'w') as f:
            f.write(updated_content)

        subprocess.check_call(['git', 'add', manifest_path])
    except (OSError, subprocess.CalledProcessError, re.error) as e:
        print(f"Error occurred while updating manifest: {e}")

if __name__ == '__main__':
    repo_root = get_repo_root()
    working_dir = get_working_dir()
    if repo_root is None or working_dir is None:
        exit(1)

    addons_changed = get_addons_changed(working_dir)
    if not addons_changed:
        print("No addons changed. Exiting.")
        exit(0)

    try:
        subprocess.check_call(['git', 'fetch', 'origin'])
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while fetching latest changes: {e}")
        exit(1)

    live_version = {}
    pre_prod_version = {}
    stage_version = {}
    for addon_dir, _ in addons_changed.items():
        addon_name = os.path.basename(addon_dir)
        live_content = get_manifest_content('origin/live', addon_dir)
        live_version[addon_name] = get_manifest_version(live_content)
        pre_prod_content = get_manifest_content('origin/pre-prod', addon_dir)
        pre_prod_version[addon_name] = get_manifest_version(pre_prod_content)
        stage_content = get_manifest_content('origin/stage', addon_dir)
        stage_version[addon_name] = get_manifest_version(stage_content)

    for addon_dir, change_amount in addons_changed.items():
        addon_name = os.path.basename(addon_dir)
        manifest_path = os.path.join(addon_dir, '__manifest__.py')
        with open(manifest_path, 'r') as f:
            content = f.read()

        current_version = get_manifest_version(content)
        if current_version:
            branch_version = current_version

            if live_version.get(addon_name) and branch_version <= live_version[addon_name]:
                continue
            if pre_prod_version.get(addon_name) and branch_version <= pre_prod_version[addon_name]:
                continue
            if stage_version.get(addon_name) and branch_version <= stage_version[addon_name]:
                continue

            new_version = manifest_increase(change_amount, current_version)
            if new_version:
                update_manifest(addon_dir, new_version)

    try:
        subprocess.check_call(['git', 'commit', '-m', 'Increment version number for modified addons'])
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while committing changes: {e}")
        exit(1)
