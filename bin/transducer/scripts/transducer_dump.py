from transducer import Transducer
from datetime import datetime
import time

if __name__ == "__main__":
    transducer = Transducer()
    start_time = datetime.now()
    start_mono = time.monotonic()
    filename = start_time.strftime("%Y%m%d_%H%M%S") + "_data.csv"
    with open(filename, "w") as f:
        try:
            while True:
                weight = transducer.read_weight()
                time_ms = int((time.monotonic() - start_mono) * 1000)
                f.write(f"{time_ms},{weight}\n")
        except KeyboardInterrupt:
            print("Data logging stopped.")

