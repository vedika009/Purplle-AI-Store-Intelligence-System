import csv
from datetime import datetime, timezone
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
        """Load POS transactions from CSV file, supporting both mock and real schemas."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 1. Normalize transaction/order ID
                    tx_id = row.get('transaction_id') or row.get('order_id')
                    
                    # 2. Normalize store ID/name
                    store_id = row.get('store_id', '')
                    store_name = row.get('store_name', '')
                    
                    # 3. Normalize amount
                    amount = row.get('amount') or row.get('total_amount') or row.get('NMV') or row.get('GMV') or row.get('basket_value_inr')
                    
                    # 4. Normalize timestamp
                    timestamp = None
                    if 'timestamp' in row and row['timestamp']:
                        try:
                            timestamp = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                        except Exception:
                            pass
                    
                    if not timestamp and 'order_date' in row and 'order_time' in row:
                        try:
                            # Real format: order_date = "10-04-2026", order_time = "16:55:36"
                            dt_str = f"{row['order_date']} {row['order_time']}"
                            timestamp = datetime.strptime(dt_str, "%d-%m-%Y %H:%M:%S").replace(tzinfo=timezone.utc)
                        except Exception:
                            pass
                            
                    if tx_id and timestamp:
                        self.transactions.append({
                            "transaction_id": tx_id,
                            "store_id": store_id,
                            "store_name": store_name,
                            "timestamp": timestamp,
                            "amount": float(amount) if amount else 0.0
                        })
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
            row_sid = txn.get('store_id', '').strip().lower() if txn.get('store_id') else ''
            row_sname = txn.get('store_name', '').strip().lower() if txn.get('store_name') else ''
            q_sid = store_id.strip().lower()
            
            # Flexible matching for store identifiers
            match = False
            if row_sid == q_sid or row_sname == q_sid:
                match = True
            elif 'brigade' in q_sid and ('brigade' in row_sid or 'brigade' in row_sname):
                match = True
            elif 'st1008' in row_sid and 'brigade' in q_sid:
                match = True
                
            if not match:
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
