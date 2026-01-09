#!/usr/bin/env python3

import sys
import re
import urllib.request
import urllib.error
import email
import datetime
from io import StringIO

def fetch_mbox(project, month):
    """Fetch mbox file for a project and month"""
    url = f"https://lists.apache.org/api/mbox.lua?list=dev@{project}.apache.org&date={month}"
    try:
        with urllib.request.urlopen(url) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching {project} mbox: {e}")
        return None

def parse_mbox(mbox_content):
    """Parse mbox content and return list of email messages"""
    messages = []
    if not mbox_content:
        return messages
    
    # Split on "From " lines that start messages
    parts = re.split(r'\nFrom ', mbox_content)
    for i, part in enumerate(parts):
        if i > 0:  # Add back the "From " for all but the first
            part = "From " + part
        try:
            msg = email.message_from_string(part)
            messages.append(msg)
        except:
            continue
    return messages

def find_vote_threads(messages, show_voted=False, emails=None):
    """Find VOTE threads and check if any specified email has voted"""
    vote_threads = {}
    
    for msg in messages:
        subject = msg.get('Subject', '')
        message_id = msg.get('Message-ID', '')
        from_addr = msg.get('From', '')
        body = str(msg.get_payload())
        
        # Look for [VOTE] in subject
        if '[VOTE]' in subject.upper():
            # Look for dist.apache.org URLs in the body
            dist_urls = re.findall(r'https://dist\.apache\.org/repos/dist/dev/[^\s<>]+', body)
            
            if dist_urls:
                thread_key = re.sub(r'^\[VOTE\]\s*', '', subject, flags=re.IGNORECASE).strip()
                if thread_key not in vote_threads:
                    vote_threads[thread_key] = {
                        'subject': subject,
                        'urls': dist_urls,
                        'email_voted': False,
                        'message_id': message_id
                    }
        
        # Check if any specified email has voted in any thread
        if emails and any(email in from_addr for email in emails) and any(word in body.lower() for word in ['+1', 'vote']):
            # Try to match this to a vote thread by subject similarity
            for thread_key in vote_threads:
                if any(word in subject.lower() for word in thread_key.lower().split()[:3]):
                    vote_threads[thread_key]['email_voted'] = True
    
    # Filter based on show_voted flag
    filtered = {}
    for key, thread in vote_threads.items():
        if show_voted == thread['email_voted']:
            filtered[key] = thread
    
    return filtered

def main():
    show_voted = '--voted' in sys.argv
    
    # Read configuration from external file
    try:
        with open('projects.txt', 'r') as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("Error: projects.txt file not found")
        sys.exit(1)
    
    # Parse emails and projects
    emails = []
    projects = []
    
    for line in lines:
        if line.startswith('email:'):
            emails.append(line.split(':', 1)[1])
        else:
            projects.append(line)
    
    if not emails:
        print("Error: No email configuration found in projects.txt")
        sys.exit(1)
    
    current_month = datetime.datetime.now().strftime('%Y-%m')
    
    print(f"Checking for [VOTE] threads in {current_month}")
    print(f"Looking for threads {', '.join(emails)} {'HAS' if show_voted else 'has NOT'} voted on\n")
    
    for project in projects:
        print(f"Checking {project}...")
        mbox_content = fetch_mbox(project, current_month)
        messages = parse_mbox(mbox_content)
        vote_threads = find_vote_threads(messages, show_voted, emails)
        
        if vote_threads:
            print(f"\n=== {project.upper()} ===")
            for thread_key, thread in vote_threads.items():
                print(f"Subject: {thread['subject']}")
                for url in thread['urls']:
                    print(f"  URL: {url}")
                print()
        else:
            print(f"  No relevant vote threads found")
    
    print("\nDone.")

if __name__ == "__main__":
    main()
