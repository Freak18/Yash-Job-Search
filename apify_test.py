from apify_client import ApifyClient

TOKEN = os.getenv("APIFY_TOKEN")

client = ApifyClient(TOKEN)

print("Apify Connected Successfully")