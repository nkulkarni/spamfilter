# Spamfilter

An automated tool that uses Grok to identify mailing list emails in Apple Mail, attempts to unsubscribe from them, and provides detailed reports.

## Features

- Uses Grok to identify mass emails and newsletters
- Automatically detects and handles unsubscribe methods
- Moves identified emails to a "Suspected Mailing List" folder
- Generates detailed reports of processed emails
- Can run hourly via cron
- Works with multiple email accounts in Apple Mail

## Prerequisites

- macOS with Apple Mail configured
- Python 3.9 or higher
- uv (Python package installer)
- Grok API key

## Installation

1. Install uv if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clone the repository:
```bash
git clone https://github.com/yourusername/spamfilter.git
cd spamfilter
```

3. Set up the virtual environment and install dependencies:
```bash
uv venv # you might need --python 3.11.6 
source .venv/bin/activate
uv pip install -r requirements.txt
```

4. Create a .env file with your OpenAI API key:
```bash
echo "GROK_API_KEY=your-key-here" > .env
```

5. Make the cron script executable:
```bash
chmod +x run_spamfilter.sh
```

## Setting Up Automatic Runs

Add this to your `~/.zshrc`:

```bash
# Set up spamfilter cron job if it doesn't exist
if ! crontab -l | grep -q "run_spamfilter.sh"; then
    (crontab -l 2>/dev/null; echo "0 * * * * /path/to/spamfilter/run_spamfilter.sh >> /path/to/spamfilter/cron.log 2>&1") | crontab -
fi

# Function to manage spamfilter cron
spamfilter_cron() {
    case $1 in
        "start")
            (crontab -l 2>/dev/null; echo "0 * * * * /path/to/spamfilter/run_spamfilter.sh >> /path/to/spamfilter/cron.log 2>&1") | crontab -
            echo "Spamfilter cron job started"
            ;;
        "stop")
            crontab -l | grep -v "run_spamfilter.sh" | crontab -
            echo "Spamfilter cron job stopped"
            ;;
        "status")
            if crontab -l | grep -q "run_spamfilter.sh"; then
                echo "Spamfilter cron job is running"
            else
                echo "Spamfilter cron job is not running"
            fi
            ;;
        *)
            echo "Usage: spamfilter_cron [start|stop|status]"
            ;;
    esac
}
```

Remember to replace `/path/to/spamfilter` with your actual path to the repository.

## Usage

### Manual Run

```bash
# From the project directory
source .venv/bin/activate
python -m spamfilter.processor
```

### Managing Cron Job

Start the hourly checks:
```bash
spamfilter_cron start
```

Stop the checks:
```bash
spamfilter_cron stop
```

Check status:
```bash
spamfilter_cron status
```

### Output

The script generates a timestamped digest file (`mail_list_digest_YYYYMMDD_HHMMSS.txt`) containing:
- List of processed emails by account
- Unsubscribe attempt results
- Statistics on successful/failed/manual unsubscribes
- List of unique senders

## Project Structure

```
spamfilter/
├── .env                    # Your API keys
├── .gitignore             # Git ignore file
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── run_spamfilter.sh     # Cron execution script
└── spamfilter/           # Python package directory
    ├── __init__.py       # Makes it a package
    └── processor.py      # Main code
```

## How It Works

1. Checks all Mail.app inboxes for unread emails
2. Uses GPT-4 to analyze each email's content and determine if it's a mailing list
3. Attempts to unsubscribe using:
   - List-Unsubscribe headers
   - Unsubscribe links in email content
   - Automated unsubscribe emails
4. Moves identified emails to a "Suspected Mailing List" folder
5. Generates a detailed report

## Monitoring

View the cron job logs:
```bash
tail -f /path/to/spamfilter/cron.log
```

## Configuration

Adjust these parameters in `processor.py`:
- GPT confidence threshold (default: 0.7)
- Folder name for mailing list emails (default: "Suspected Mailing List")
- Content length limit for GPT analysis (default: 4000 characters)

## Development

To modify the code:
1. Activate the virtual environment:
```bash
source .venv/bin/activate
```

2. Make your changes
3. Test manually by running:
```bash
python -m spamfilter.processor
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT

## Disclaimer

This tool interacts with your email and makes automated decisions. While it's designed to be safe, always monitor its behavior initially and adjust as needed.# spamfilter
