#!/usr/bin/env python3

import sys
import re
import urllib.request
import urllib.error
import hashlib
import subprocess
import tarfile
import datetime
import shutil
import glob
import platform
from pathlib import Path

def download_file(url, filename):
    try:
        urllib.request.urlretrieve(url, filename)
        return True
    except Exception as e:
        print(f"Error downloading {filename}: {e}")
        return False

def verify_hashes(filename):
    """Verify all available hash files for a given archive"""
    hash_results = {}
    
    # Look for all hash files for this archive
    for hash_file in glob.glob(f"{filename}.sha*"):
        # Extract hash type from filename (e.g., sha1, sha256, sha512)
        hash_type = hash_file.split('.')[-1]
        if hash_type.startswith('sha'):
            hash_num = hash_type[3:]  # Get the number part (1, 256, 512, etc.)
            
            try:
                # Choose appropriate command based on OS and hash type
                if platform.system().lower() == 'linux':
                    if hash_num == '1':
                        cmd = ['sha1sum', filename]
                    else:
                        cmd = [f"sha{hash_num}sum", filename]
                else:
                    # macOS and others use shasum
                    if hash_num == '1':
                        cmd = ['shasum', filename]  # SHA1 is default for shasum
                    else:
                        cmd = ['shasum', '-a', hash_num, filename]
                
                # Get actual hash using appropriate command
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    hash_results[hash_type] = False
                    continue
                    
                actual = result.stdout.split()[0].lower()
                
                with open(hash_file, 'r') as f:
                    content = f.read().strip()
                    # Split by colon to separate filename from hash, then extract hex from hash part
                    if ':' in content:
                        hash_part = content.split(':', 1)[1]
                    else:
                        hash_part = content
                    
                    hex_chars = re.findall(r'[a-fA-F0-9]', hash_part)
                    expected_length = int(hash_num) // 4 if hash_num != '1' else 40  # SHA1 is 160 bits = 40 hex chars
                    
                    if len(hex_chars) >= expected_length:
                        expected = ''.join(hex_chars[:expected_length]).lower()
                        if actual != expected:
                            print(f"\n  {hash_type.upper()} MISMATCH for {filename}:")
                            print(f"  Expected: {highlight_diff(expected, actual, expected)}")
                            print(f"  Actual:   {highlight_diff(actual, expected, actual)}")
                            hash_results[hash_type] = False
                        else:
                            hash_results[hash_type] = True
                    else:
                        hash_results[hash_type] = False
            except Exception:
                hash_results[hash_type] = False
    
    return hash_results

def highlight_diff(text1, text2, display_text):
    """Highlight differences between two strings using ANSI color codes"""
    RED = '\033[91m'
    RESET = '\033[0m'
    
    result = ""
    for i, char in enumerate(display_text):
        if i < len(text2) and char != text2[i]:
            result += f"{RED}{char}{RESET}"
        else:
            result += char
    return result

def verify_gpg(filename, base_url):
    asc_file = f"{filename}.asc"
    if not Path(asc_file).exists():
        return None
    
    try:
        result = subprocess.run(['gpg', '--verify', asc_file, filename], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            return True
        else:
            # GPG verification failed, look for KEYS file
            print(f"\n  GPG verification failed for {filename}")
            print(f"  Error: {result.stderr.strip()}")
            
            # Extract project name from URL path
            # URL format: https://dist.apache.org/repos/dist/dev/PROJECT/...
            # or: https://dist.apache.org/repos/dist/dev/incubator/PROJECT/...
            url_parts = base_url.split('/')
            if 'dist' in url_parts and 'dev' in url_parts:
                dev_index = url_parts.index('dev')
                if dev_index + 1 < len(url_parts):
                    if url_parts[dev_index + 1] == 'incubator' and dev_index + 2 < len(url_parts):
                        # Incubator project
                        project = url_parts[dev_index + 2]
                        keys_url = f"https://downloads.apache.org/incubator/{project}/KEYS"
                    else:
                        # Top-level project
                        project = url_parts[dev_index + 1]
                        keys_url = f"https://downloads.apache.org/{project}/KEYS"
                    
                    try:
                        print(f"  Attempting to download KEYS file from {keys_url}")
                        
                        # Backup existing KEYS file if it exists
                        if Path("KEYS").exists():
                            Path("KEYS").rename("KEYS.bak")
                            print(f"  Backed up existing KEYS file to KEYS.bak")
                        
                        download_file(keys_url, "KEYS")
                        if Path("KEYS").exists():
                            print(f"  ✓ Downloaded KEYS file")
                            print(f"  Please run: gpg --import KEYS")
                            print(f"  Then re-run the verification")
                        else:
                            print(f"  ✗ Could not download KEYS file")
                    except Exception as e:
                        print(f"  ✗ Error downloading KEYS file: {e}")
            
            return False
    except Exception:
        return False

def extract_and_check_license(archive):
    try:
        with tarfile.open(archive, 'r:*') as tar:
            tar.extractall(filter='data')
            # Get the top-level directory name
            members = tar.getnames()
            if not members:
                return None, None, None
            
            top_dir = members[0].split('/')[0]
            top_path = Path(top_dir)
            
            # Check for LICENSE file (with or without .txt extension)
            license_path = None
            for name in ['LICENSE', 'LICENSE.txt']:
                path = top_path / name
                if path.exists():
                    license_path = path
                    break
            has_license = license_path is not None
            
            # Check for NOTICE file (with or without .txt extension)
            notice_path = None
            for name in ['NOTICE', 'NOTICE.txt']:
                path = top_path / name
                if path.exists() and path.stat().st_size > 0:
                    notice_path = path
                    break
            has_notice = notice_path is not None
            
            current_year = str(datetime.datetime.now().year)
            notice_has_current_year = False
            
            if has_notice:
                try:
                    with open(notice_path, 'r') as f:
                        notice_content = f.read()
                        notice_has_current_year = current_year in notice_content
                except Exception:
                    pass
            
            return has_license, has_notice, notice_has_current_year
    except Exception as e:
        print(f"Error extracting {archive}: {e}")
        return False, False, False

def cleanup():
    """Remove all downloaded files and extracted directories"""
    removed = []
    
    # First, identify extracted directories by checking what archives exist/existed
    extracted_dirs = set()
    for pattern in ['*.tgz', '*.tar.gz']:
        for archive in glob.glob(pattern):
            try:
                with tarfile.open(archive, 'r:*') as tar:
                    members = tar.getnames()
                    if members:
                        top_dir = members[0].split('/')[0]
                        extracted_dirs.add(top_dir)
            except:
                pass
    
    # Remove extracted directories
    for dir_name in extracted_dirs:
        if Path(dir_name).is_dir():
            shutil.rmtree(dir_name)
            removed.append(f"{dir_name}/")
    
    # Remove archive files and signatures
    for pattern in ['*.tgz', '*.tar.gz', '*.asc', '*.sha*']:
        for file in glob.glob(pattern):
            Path(file).unlink()
            removed.append(file)
    
    # Remove downloaded HTML and robots.txt files
    for file in ['index.html', 'robots.txt', 'KEYS', 'KEYS.bak']:
        if Path(file).exists():
            Path(file).unlink()
            removed.append(file)
    
    if removed:
        print("Cleaned up:")
        for item in removed:
            print(f"  {item}")
    else:
        print("Nothing to clean up")

def main():
    if len(sys.argv) == 2 and sys.argv[1] == '--cleanup':
        cleanup()
        return
    
    if len(sys.argv) != 2:
        print("Usage: python3 verify_release.py <URL>")
        print("       python3 verify_release.py --cleanup")
        sys.exit(1)
    
    url = sys.argv[1].rstrip('/')
    
    # Get directory listing
    try:
        with urllib.request.urlopen(url) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching URL: {e}")
        sys.exit(1)
    
    # Extract file links
    files = re.findall(r'href="([^"]*\.(?:tgz|tar\.gz|sha\d+|sha1|asc))"', html)
    
    if not files:
        print("No files found")
        sys.exit(1)
    
    # Download files
    for filename in files:
        if Path(filename).exists():
            print(f"Skipping {filename} (already exists)")
        else:
            print(f"Downloading {filename}...")
            download_file(f"{url}/{filename}", filename)
    
    # Verify archives
    archives = [f for f in files if f.endswith(('.tgz', '.tar.gz'))]
    results = []
    
    for archive in archives:
        if not Path(archive).exists():
            continue
            
        sha_ok = verify_hashes(archive)
        gpg_ok = verify_gpg(archive, url)
        
        print(f"Extracting {archive}...")
        has_license, has_notice, notice_current_year = extract_and_check_license(archive)
        
        results.append({
            'file': archive,
            'hashes': sha_ok,
            'gpg': gpg_ok,
            'license': has_license,
            'notice': has_notice,
            'notice_current_year': notice_current_year
        })
    
    # Generate report
    print("\n=== VERIFICATION REPORT ===")
    verified_files = []
    
    for result in results:
        print(f"\nFile: {result['file']}")
        
        # Display hash verification results
        if result['hashes']:
            for hash_type, status in result['hashes'].items():
                print(f"  {hash_type.upper()}: {'✓' if status else '✗'}")
        else:
            print(f"  Hashes: N/A")
            
        print(f"  GPG:     {'✓' if result['gpg'] else '✗' if result['gpg'] is False else 'N/A'}")
        print(f"  LICENSE: {'✓' if result['license'] else '✗' if result['license'] is False else 'N/A'}")
        print(f"  NOTICE:  {'✓' if result['notice'] else '✗' if result['notice'] is False else 'N/A'}")
        if result['notice'] and result['notice_current_year'] is not None:
            year_status = "✓" if result['notice_current_year'] else "⚠"
            print(f"  Current Year: {year_status}")
        
        # Track successfully verified files (all hashes pass and GPG passes)
        all_hashes_pass = result['hashes'] and all(result['hashes'].values())
        if all_hashes_pass and result['gpg']:
            verified_files.append(result['file'])
    
    # Output boilerplate vote response
    if verified_files:
        print("\n=== COPY-PASTE VOTE RESPONSE ===")
        print("+1 (non-binding)")
        print()
        print(f"* Verified signatures and hashes on the following files as per https://apache.org/info/verification.html")
        
        for result in results:
            if result['file'] in verified_files:
                verifications = []
                
                # Add hash verifications
                if result['hashes']:
                    for hash_type in result['hashes'].keys():
                        verifications.append(hash_type.upper())
                
                # Add GPG verification
                if result['gpg']:
                    verifications.append("GPG signature")
                
                verification_text = ", ".join(verifications)
                print(f"  - {result['file']} ({verification_text})")
        
        print("* Verified LICENSE and NOTICE files")

if __name__ == "__main__":
    main()
