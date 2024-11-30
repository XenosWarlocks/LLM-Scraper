# api_limiting.py

from functools import wraps
import time

def rate_limit(calls: int, period: float):
    last_reset = time.time()
    calls_made = 0

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal last_reset, calls_made
            
            current = time.time()
            elapsed = current - last_reset
            
            # Reset the count if the period has passed
            if elapsed > period:
                calls_made = 0
                last_reset = current
            
            # If the call limit is reached, wait for the period to reset
            if calls_made >= calls:
                sleep_time = period - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                calls_made = 0
                last_reset = time.time()
            
            calls_made += 1
            return func(*args, **kwargs)
        
        return wrapper
    return decorator