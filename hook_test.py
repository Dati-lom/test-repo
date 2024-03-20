import os
import re
import subprocess

# Define the pattern to match the version in the manifest file
VERSION_PATTERN = r"'version': '(\d+\.\d+)\.(\d+)\.(\d+)\.(\d+)'"

# Define the thresholds for change types
PATCH_THRESHOLD = 50
FEATURE_THRESHOLD = 100

def get_repo_root():
    return subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).decode('utf-8').strip() 

def get_addons_dir(repo_root):
    ls_files_output = subprocess.check_output(['git', 'ls-files'])
    all_files = ls_files_output.decode('utf-8').split('\n')

    # Filtering only manifest files
    manifest_files = [file_path for file_path in all_files if file_path.endswith('__manifest__.py')]

    # 
    addons_dirs = set(os.path.dirname(os.path.join(repo_root, manifest_path)) for manifest_path in manifest_files)

    return list(addons_dirs)


def get_modified_files_and_changes(addons_dir):
    # Use 'git diff' to find the modified files and line changes
    diff_output = subprocess.check_output(['git', 'diff', '--numstat', 'HEAD'])
    diff_lines = diff_output.decode('utf-8').split('\n')

    file_changes = {}
    for line in diff_lines:
        if line:
            added, removed, file_path = line.split('\t')
            if file_path.startswith(addons_dir) and (file_path.endswith('.py') or file_path.endswith('.xml') or file_path.endswith('.csv') or file_path.endswith('.po')):
                total_changes = int(added) + int(removed)
                if total_changes >= FEATURE_THRESHOLD:
                    change_type = 'breaking'
                elif total_changes >= PATCH_THRESHOLD:
                    change_type = 'feature'
                else:
                    change_type = 'fix'
                file_changes[file_path] = change_type

    return file_changes

def get_branch_version(branch_name):
    manifest_content = subprocess.check_output(['git', 'show', f'origin/{branch_name}:/*/\__manifest\__.py'])
    match = re.search(VERSION_PATTERN, manifest_content.decode('utf-8'))
    if match:
        return '.'.join(match.group(1, 2, 3, 4))
    return None

def increment_version(current_version, change_type):
    """
    Increment the version number based on the specified change_type.
    """
    odoo_version_main,odoo_version_sub, x, y, z = current_version.split('.')
    if change_type == 'breaking':
        new_x = str(int(x) + 1)
        new_y = '0'
        new_z = '0'
    elif change_type == 'feature':
        new_x = x
        new_y = str(int(y) + 1)
        new_z = '0'
    else:  # change_type == 'fix'
        new_x = x
        new_y = y
        new_z = str(int(z) + 1)
    new_version = '.'.join([odoo_version_main,odoo_version_sub, new_x, new_y, new_z])
    return new_version

def update_manifest(addon_name, addons_dir, new_version):
    """
    Update the version number in the __manifest__.py file.
    """
    manifest_path = os.path.join(addons_dir, addon_name, '__manifest__.py')
    with open(manifest_path, 'r') as f:
        content = f.read()

    updated_content = re.sub(VERSION_PATTERN, f"'version': '{new_version}'", content)

    with open(manifest_path, 'w') as f:
        f.write(updated_content)

    # Stage the changes
    subprocess.check_call(['git', 'add', manifest_path])

if __name__ == '__main__':
    repo_root = get_repo_root()
    addons_dir = get_addons_dir(repo_root)
    file_changes = get_modified_files_and_changes(addons_dir)

    # Fetch the latest changes from the remote branches
    subprocess.check_call(['git', 'fetch', 'origin'])

    # Get the version numbers from the live, pre-prod, and stage branches
    live_version = get_branch_version('live')
    pre_prod_version = get_branch_version('pre-prod')
    stage_version = get_branch_version('stage')

    updated_addons = set()
    addons_to_update = set()
    for file_path, change_type in file_changes.items():
        addon_name = os.path.dirname(file_path).split('/')[-1]
        if addon_name not in updated_addons:
            manifest_path = os.path.join(addons_dir, addon_name, '__manifest__.py')
            with open(manifest_path, 'r') as f:
                content = f.read()

            match = re.search(VERSION_PATTERN, content)
            if match:
                current_version = '.'.join(match.group(1, 2, 3, 4))
                branch_version = current_version

                # Check if the branch version is greater than the live, pre-prod, and stage versions
                if live_version and branch_version <= live_version:
                    continue
                if pre_prod_version and branch_version <= pre_prod_version:
                    continue
                if stage_version and branch_version <= stage_version:
                    continue

                addons_to_update.add(addon_name)

    for addon_name in addons_to_update:
        manifest_path = os.path.join(addons_dir, addon_name, '__manifest__.py')
        with open(manifest_path, 'r') as f:
            content = f.read()

        match = re.search(VERSION_PATTERN, content)
        if match:
            current_version = '.'.join(match.group(1, 2, 3, 4))
            change_type = file_changes[os.path.join(addons_dir, addon_name, '__manifest__.py')]
            new_version = increment_version(current_version, change_type)
            update_manifest(addon_name, addons_dir, new_version)
            updated_addons.add(addon_name)

    # Create a new commit for the version increments
    subprocess.check_call(['git', 'commit', '-m', 'Increment version number for modified addons'])