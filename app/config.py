import os
from dataclasses import dataclass
@dataclass(frozen=True)
class Settings:
    poll_seconds:int=int(os.getenv("POLL_SECONDS","60"))
    timezone:str=os.getenv("TIMEZONE","Asia/Kolkata")
    weekly_offset:float=float(os.getenv("WEEKLY_OFFSET","0.002"))
    rolling_rr:float=float(os.getenv("ROLLING_RR","1.5"))
    weekly_rr:float=float(os.getenv("WEEKLY_RR","1.5"))
    weekly_orb_rr:float=float(os.getenv("WEEKLY_ORB_RR","1.5"))
    monthly_orb_rr:float=float(os.getenv("MONTHLY_ORB_RR","1.0"))
settings=Settings()
