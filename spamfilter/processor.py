from Foundation import *
from ScriptingBridge import *
from datetime import datetime
import re
import os
import openai
import html2text
import urllib.parse
import requests
from bs4 import BeautifulSoup
import webbrowser
from dataclasses import dataclass
from typing import List, Optional
import json
from dotenv import load_dotenv
import traceback

@dataclass
class UnsubscribeResult:
    sender: str
    subject: str
    status: str  # 'success', 'failed', 'manual_required'
    unsubscribe_method: str  # 'link', 'email', 'manual'
    details: str

class MailProcessor:
    def __init__(self, api_key):
        self.mail = SBApplication.applicationWithBundleIdentifier_("com.apple.mail")
        self.client = openai.OpenAI(api_key=api_key, base_url="https://api.x.ai/v1",)
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False  # Keep links for unsubscribe detection
        self.processed_senders = set()
        self.unsubscribe_results: List[UnsubscribeResult] = []

    def get_all_inboxes(self):
        """Get all inbox accounts in Mail."""
        accounts = self.mail.accounts()
        inboxes = []
        for account in accounts:
            if account.enabled():
                mailboxes = account.mailboxes()
                for mailbox in mailboxes:
                    if mailbox.name() == "INBOX":
                        inboxes.append({
                            'account': account.name(),
                            'inbox': mailbox
                        })
        return inboxes

    def create_or_get_folder(self, account, folder_name="Suspected Mailing List"):
        """Create or get the mailing list folder for an account."""
        # First check if folder exists
        for mailbox in account.mailboxes():
            if mailbox.name() == folder_name:
                return mailbox
                
        # If folder doesn't exist, create it using AppleScript
        script = f'''
        tell application "Mail"
            tell account "{account.name()}"
                if not (exists mailbox "{folder_name}") then
                    make new mailbox with properties {{name:"{folder_name}"}}
                end if
                return mailbox "{folder_name}"
            end tell
        end tell
        '''
        
        os.system(f"osascript -e '{script}'")
        
        # Check again for the folder and return it
        for mailbox in account.mailboxes():
            if mailbox.name() == folder_name:
                return mailbox
        
        print(f"Warning: Could not create mailbox '{folder_name}' for account {account.name()}")
        # Return INBOX as fallback
        for mailbox in account.mailboxes():
            if mailbox.name() == "INBOX":
                return mailbox
        
        return None

    def extract_unsubscribe_info(self, message, html_content):
        """Extract unsubscribe information from the email."""
        # Convert html_content to string if it's an SBObject
        if hasattr(html_content, 'stringValue'):
            html_content = str(html_content.stringValue())
        elif hasattr(html_content, 'content'):
            html_content = str(html_content.content())
        
        # Ensure html_content is a string
        html_content = str(html_content)
        
        # Debug print
        print(f"HTML Content type: {type(html_content)}")
        print(f"HTML Content length: {len(html_content)}")
        
        # Proceed with BeautifulSoup parsing
        soup = BeautifulSoup(html_content, 'html.parser')
        unsubscribe_keywords = ['unsubscribe', 'opt out', 'opt-out', 'remove me']
        
        headers = message.headers()
        
        # Check List-Unsubscribe header
        list_unsubscribe = None
        header_str = str(headers)
        match = re.search(r'List-Unsubscribe:\s*<([^>]+)>', header_str)
        if match:
            list_unsubscribe = match.group(1)
            if list_unsubscribe.startswith('mailto:'):
                return {'method': 'email', 'target': list_unsubscribe[7:]}
            elif list_unsubscribe.startswith('http'):
                return {'method': 'link', 'target': list_unsubscribe}

        for keyword in unsubscribe_keywords:
            links = soup.find_all('a', text=re.compile(keyword, re.I))
            for link in links:
                href = link.get('href')
                if href and href.startswith(('http', 'mailto:')):
                    return {
                        'method': 'link' if href.startswith('http') else 'email',
                        'target': href
                    }

        return {'method': 'manual', 'target': None}

    def attempt_unsubscribe(self, message, html_content):
        """Attempt to unsubscribe from the mailing list."""
        sender = str(message.sender())
        subject = str(message.subject())        
        try:
            unsubscribe_info = self.extract_unsubscribe_info(message, html_content)
            
            if unsubscribe_info['method'] == 'link':
                # For link-based unsubscribe, open in browser for manual action
                webbrowser.open(unsubscribe_info['target'])
                result = UnsubscribeResult(
                    sender=sender,
                    subject=subject,
                    status='manual_required',
                    unsubscribe_method='link',
                    details=f"Unsubscribe link opened in browser: {unsubscribe_info['target']}"
                )
            
            elif unsubscribe_info['method'] == 'email':
                # Create and send unsubscribe email
                unsubscribe_message = self.mail.OutgoingMessage.alloc().init()
                unsubscribe_message.setSubject_('Unsubscribe')
                unsubscribe_message.setContent_('Please unsubscribe me from this mailing list.')
                
                recipient = unsubscribe_message.ToRecipient.alloc().init()
                recipient.setAddress_(unsubscribe_info['target'])
                unsubscribe_message.setToRecipients_([recipient])
                
                unsubscribe_message.send()
                
                result = UnsubscribeResult(
                    sender=sender,
                    subject=subject,
                    status='success',
                    unsubscribe_method='email',
                    details=f"Unsubscribe email sent to {unsubscribe_info['target']}"
                )
            
            else:
                result = UnsubscribeResult(
                    sender=sender,
                    subject=subject,
                    status='failed',
                    unsubscribe_method='manual',
                    details="No automated unsubscribe method found"
                )
            
            self.unsubscribe_results.append(result)
            return result
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            result = UnsubscribeResult(
                sender=sender,
                subject=subject,
                status='failed',
                unsubscribe_method=None,
                details=f"Error: {str(e)}\n\nFull Traceback:\n{error_traceback}"
            )
            print(f"Unsubscribe attempt failed: {error_traceback}")
            self.unsubscribe_results.append(result)
            return result

    def clean_email_content(self, html_content):
        """Convert HTML to plain text and clean it up."""
        text = self.h2t.handle(html_content)
        return text[:4000]  # Limit content length for API

    def is_mailing_list(self, message):
        """Use GPT to determine if a message is from a mailing list."""
        try:
            # First check headers for obvious list markers
            headers = message.headers()
            list_headers = ['List-Unsubscribe', 'List-ID', 'Precedence: bulk', 'X-Campaign']
            for header in list_headers:
                if header.lower() in str(headers).lower():
                    return True

            # Get message content and metadata
            content = self.clean_email_content(str(message.content()))
            sender = message.sender()
            subject = message.subject()
            to_addresses = [addr.address() for addr in message.toRecipients()]
            cc_addresses = [addr.address() for addr in message.ccRecipients()]

            # Construct prompt for GPT
            prompt = f"""Analyze this email and determine if it's a mass email/newsletter/mailing list or a personal email specifically meant for the recipient.

Email metadata:
From: {sender}
To: {', '.join(to_addresses)}
CC: {', '.join(cc_addresses)}
Subject: {subject}

Email content:
{content}

Consider factors like:
- Whether the content is personalized
- Presence of unsubscribe links/text
- Marketing or newsletter-style formatting
- Whether it addresses the recipient specifically
- Mass announcement characteristics

Respond with either 'mailing_list' or 'personal' followed by a confidence score (0-1), separated by a comma.
Example: 'mailing_list,0.95' or 'personal,0.88'"""

            # Define a tool for structured classification output
            classification_tool = {
                "type": "function",
                "function": {
                    "name": "classify_email",
                    "description": "Classify an email as either a mailing list or not a mailing list, with a confidence score",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "classification": {
                                "type": "string", 
                                "enum": ["mailing_list", "not_mailing_list"],
                                "description": "Whether the email is a mailing list or not"
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Confidence score of the classification (0-1)"
                            }
                        },
                        "required": ["classification", "confidence"]
                    }
                }
            }
            
            # Get GPT's analysis using function calling
            response = self.client.chat.completions.create(
                model="grok-2-latest",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                tools=[classification_tool],
                tool_choice={"type": "function", "function": {"name": "classify_email"}},
                temperature=0,
            )
            
            # Extract the tool call result
            tool_call = response.choices[0].message.tool_calls[0]
            result = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
            classification = result.get('classification', None)
            confidence = result.get('confidence', 0)

            # Consider it a mailing list if classified as such with confidence > 0.7
            return classification == 'mailing_list' and confidence > 0.7

        except Exception as e:
            print(f"Error analyzing message: {str(e)}, {response.choices}")
            # Fall back to header-based detection
            return any(header.lower() in str(headers).lower() for header in list_headers)

    def process_unread_emails(self):
        """Process all unread emails across all inboxes."""
        inboxes = self.get_all_inboxes()
        results = []
        
        for inbox_info in inboxes:
            account_name = inbox_info['account']
            inbox = inbox_info['inbox']
            
            account = None
            for acc in self.mail.accounts():
                if acc.name() == account_name:
                    account = acc
                    break
            
            if not account:
                continue
                
            mailing_list_folder = self.create_or_get_folder(account)
            
            messages = inbox.messages()
            for message in messages:
                if message.readStatus() == False:  # unread
                    sender = message.sender()
                    subject = message.subject()
                    html_content = message.content()
                    
                    if self.is_mailing_list(message):
                        # Attempt to unsubscribe
                        unsubscribe_result = self.attempt_unsubscribe(message, html_content)
                        
                        # Move to mailing list folder
                        message.moveTo_(mailing_list_folder)
                        
                        # Add to results
                        self.processed_senders.add(sender)
                        results.append({
                            'account': account_name,
                            'sender': sender,
                            'subject': subject,
                            'unsubscribe_result': unsubscribe_result
                        })
        
        return results

    def generate_digest(self, results):
        """Generate a comprehensive digest of processed emails and unsubscribe attempts."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'mail_list_digest_{timestamp}.txt'
        
        with open(filename, 'w') as f:
            f.write(f"Mail List Processing Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            # Group by account
            by_account = {}
            for result in results:
                account = result['account']
                if account not in by_account:
                    by_account[account] = []
                by_account[account].append(result)
            
            # Write results by account
            for account, messages in by_account.items():
                f.write(f"\nAccount: {account}\n")
                f.write("-" * 40 + "\n")
                for msg in messages:
                    f.write(f"From: {msg['sender']}\n")
                    f.write(f"Subject: {msg['subject']}\n")
                    if 'unsubscribe_result' in msg:
                        ur = msg['unsubscribe_result']
                        f.write(f"Unsubscribe Status: {ur.status}\n")
                        f.write(f"Unsubscribe Method: {ur.unsubscribe_method}\n")
                        f.write(f"Details: {ur.details}\n")
                    f.write("\n")
            
            # Unsubscribe Summary
            f.write("\nUnsubscribe Summary:\n")
            f.write("-" * 40 + "\n")
            
            success_count = sum(1 for r in self.unsubscribe_results if r.status == 'success')
            manual_count = sum(1 for r in self.unsubscribe_results if r.status == 'manual_required')
            failed_count = sum(1 for r in self.unsubscribe_results if r.status == 'failed')
            
            f.write(f"Successfully unsubscribed: {success_count}\n")
            f.write(f"Manual action required: {manual_count}\n")
            f.write(f"Failed attempts: {failed_count}\n\n")
            
            # Detailed results by status
            for status in ['success', 'manual_required', 'failed']:
                status_results = [r for r in self.unsubscribe_results if r.status == status]
                if status_results:
                    f.write(f"\n{status.upper()} Results:\n")
                    for result in status_results:
                        f.write(f"Sender: {result.sender}\n")
                        f.write(f"Subject: {result.subject}\n")
                        f.write(f"Method: {result.unsubscribe_method}\n")
                        f.write(f"Details: {result.details}\n")
                        f.write("\n")
            
            # Unique senders summary
            f.write("\nUnique Senders Summary:\n")
            f.write("-" * 40 + "\n")
            for sender in sorted(self.processed_senders):
                f.write(f"{sender}\n")
        
        return filename

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    api_key = os.getenv('GROK_API_KEY')
    if not api_key:
        raise ValueError("Please set GROK_API_KEY environment variable")
        
    processor = MailProcessor(api_key)
    results = processor.process_unread_emails()
    digest_file = processor.generate_digest(results)
    print(f"Processing complete. Digest saved to: {digest_file}")

if __name__ == "__main__":
    main()