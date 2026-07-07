from transducer import Transducer


if __name__ == "__main__":
    transducer = Transducer()
    
    input("Empty the transducer and press Enter to zero: ")
    transducer.zero_weight()
    
    weight = int(input("Enter the calibration weight: "))
    print(f"Calibrating with weight: {weight}")
    input("Place the calibration weight on the transducer and press Enter to continue: ")
    transducer.set_weight(weight)
    print("Calibration completed.")
