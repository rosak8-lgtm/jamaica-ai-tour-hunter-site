"""Private operator CLI to moderate JAMAICA hotel reviews on Oracle.

Never make this endpoint public. Prints the pending content only to the
administrator's terminal. It does not send customer data to GitHub.
"""
import argparse
import json
import os
from pathlib import Path

from backend.hotel_reviews_store import HotelReviews

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--db",required=True)
    parser.add_argument("--directory",required=True)
    parser.add_argument("action",choices=("pending","approve","reject"))
    parser.add_argument("--review-id",default="")
    parser.add_argument("--reason",default="")
    args=parser.parse_args()
    store=HotelReviews(Path(args.db),Path(args.directory),
                       os.getenv("JAMAICA_REVIEW_HASH_SECRET",""))
    if args.action=="pending":
        print(json.dumps(store.pending(),ensure_ascii=False,indent=2))
    else:
        if not args.review_id:
            raise SystemExit("REVIEW_ID_REQUIRED")
        result=store.moderate(args.review_id,args.action=="approve",args.reason)
        print("REVIEW_MODERATION_UPDATED="+str(bool(result)))
        if not result:
            raise SystemExit(2)

if __name__=="__main__":main()
