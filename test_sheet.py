from sheets import get_gspread_client

gc = get_gspread_client()

sheet = gc.open("Job Scrapping")

worksheet = sheet.sheet1

worksheet.append_row([
    "Java Developer",
    "Verizon",
    "https://example.com",
    "95",
    "2026-06-06",
])

print("Row Added Successfully")
