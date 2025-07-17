# Discord Status Bot

A Discord bot that polls team members nightly to check if they're available for work sessions.

## Railway Deployment

### Prerequisites
1. A Railway account
2. A Discord bot token
3. Discord user IDs of team members
4. Discord channel ID for status updates

### Environment Variables
Set these in your Railway project settings:

**Required:**
- `DISCORD_TOKEN` - Your Discord bot token
- `MEMBER_IDS` - Comma-separated list of Discord user IDs (e.g., 12345678987654321)
- `STATUS_CHANNEL_ID` - Discord channel ID for status updates

**Optional:**
- `POLL_HOUR` - Hour to poll (default: 20 for 8PM)
- `POLL_MINUTE` - Minute to poll (default: 59)
- `TIMEOUT_MIN` - Response window in minutes (default: 15)
- `KILL_FILE` - Killswitch file path (default: ./bot_disabled)

### Deployment Steps
1. Connect your GitHub repository to Railway
2. Railway will automatically detect the Python project
3. Set the environment variables in the Railway dashboard
4. Deploy!

### Bot Commands
- `!off` - Disable automatic polling
- `!on` - Re-enable automatic polling

## Local Development
```bash
pip install -r requirements.txt
python status_bot.py
``` 