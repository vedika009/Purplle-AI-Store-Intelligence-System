import csv
from datetime import datetime
from typing import List, Dict, Optional

class POSCorrelator:
    """
    Correlates generated store events with Point of Sale (POS) transactions.
    Used to distinguish between BILLING_QUEUE_ABANDON and actual conversions.
    """
    def __init__(self, correlation_window_minutes: int = 5):
        self.transactions: List[Dict] = []
        self.correlation_window_minutes = correlation_window_minutes
        
    def load_transactions(self, file_path: str):
        """Load POS transactions from CSV file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Expected format: transaction_id, store_id, timestamp, amount
                    row['timestamp'] = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                    self.transactions.append(row)
            # Sort by timestamp
            self.transactions.sort(key=lambda x: x['timestamp'])
        except FileNotFoundError:
            pass # Handle gracefully if no pos data available yet

    def check_correlation(self, store_id: str, zone_exit_time: datetime) -> bool:
        """
        Check if there is a POS transaction within the correlation window 
        following the zone exit time.
        """
        if not self.transactions:
            return False
            
        window_end_time = zone_exit_time.timestamp() + (self.correlation_window_minutes * 60)
        
        for txn in self.transactions:
            if txn['store_id'] != store_id:
                continue
                
            txn_time = txn['timestamp'].timestamp()
            
            # If transaction is strictly before exit, ignore it
            # (Assuming transaction happens *after* they finish in queue, 
            #  or around the same time they exit the queue zone)
            if txn_time < zone_exit_time.timestamp() - 60: # 1 min grace period before exit
                continue
                
            # If transaction is beyond the window, we can stop checking 
            # (since transactions are sorted)
            if txn_time > window_end_time:
                break
                
            # Valid correlation found
            return True
            
        return False
