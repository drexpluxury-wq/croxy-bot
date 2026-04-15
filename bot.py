# ========== RUN BOT ==========
if __name__ == "__main__":
    TOKEN = os.environ.get('DISCORD_TOKEN')
    
    if not TOKEN:
        print("❌ ERROR: DISCORD_TOKEN not set in environment variables")
        print("Please add it in Render Dashboard -> Environment tab")
        exit(1)
    
    print("Starting keep-alive system...")
    start_keep_alive()
    
    print("Starting Discord bot...")
    bot.run(TOKEN)
