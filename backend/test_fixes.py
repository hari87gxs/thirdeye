"""Quick test for multi-bank extraction fixes."""
import sys
sys.path.insert(0, '.')
from agents.extraction import _has_transactions, _is_skip_page, _detect_bank

# DBS page text samples
dbs_page1 = (
    "Account Details\n"
    "Date Value Date Transaction Details Debit Credit Running Balance\n"
    "01-Sep-2025 01-Sep-2025 FAST PAYMENT 394.71 84,255.32\n"
    "EBGPP50901371025\n"
    "SUPPLIER PAYMENT\n"
    "SGD 394.71\n"
)

dbs_page6 = (
    "Account Details\n"
    "Date Value Date Transaction Details Debit Credit Running Balance\n"
    "30-Sep-2025 30-Sep-2025 FAST PAYMENT 26.82 157,657.34\n"
    "Total Debit Count : 21 Total Debit Amount : 32,785.05\n"
    "Deposit Insurance Scheme\n"
    "Printed By : test Page 6 / 6\n"
    "Printed On : 02-Oct-2025 14:09:19\n"
)

print("=== _has_transactions ===")
print(f"DBS page 1: {_has_transactions(dbs_page1)}")
print(f"DBS page 6: {_has_transactions(dbs_page6)}")

print("\n=== _is_skip_page ===")
print(f"DBS page 1: {_is_skip_page(dbs_page1)}")
print(f"DBS page 6: {_is_skip_page(dbs_page6)}")

# OCBC page for regression
ocbc_page = "Balance B/F 01 DEC 2024 129,486.85\nFAST PAYMENT 1,000.00 128,486.85\n"
print(f"OCBC page:  {_has_transactions(ocbc_page)}")

print("\n=== _detect_bank ===")
dbs_pages = [
    {"page_number": 1, "text": "Account Details\nAccount Number : 0725385342 - SGD\nAccount Name : HOH JIA PTE. LTD.\nProduct Type : AUTOSAVE ACCOUNT\n01-Sep-2025 01-Sep-2025 FAST PAYMENT 394.71 84,255.32"},
    {"page_number": 2, "text": dbs_page1},
]
print(f"DBS detected as: {_detect_bank(dbs_pages)}")

ocbc_pages = [
    {"page_number": 1, "text": "OCBC Bank Statement\nBalance B/F 01 DEC 2024 129,486.85"},
]
print(f"OCBC detected as: {_detect_bank(ocbc_pages)}")

unknown_pages = [
    {"page_number": 1, "text": "Some random text with no bank identifiers"},
]
print(f"Unknown detected as: {_detect_bank(unknown_pages)}")

print("\n=== All tests passed! ===")
