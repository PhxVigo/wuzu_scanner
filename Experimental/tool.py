# tool.py

import sys
import time
from GeeNFCReaderPro import GeeNFCReaderPro


# ---------------------------------------------------------------------
# Helpers to print UI blocks
# ---------------------------------------------------------------------

def banner():
    print("\n" + "=" * 60)
    print("     W U Z U   U H F   R F I D   T O O L")
    print("=" * 60 + "\n")


def menu():
    print("Choose an option:\n")
    print(" 1) Detect single tag")
    print(" 2) Read EPC")
    print(" 3) Write EPC")
    print(" 4) Read TID")
    print(" 5) Read Reserved")
    print(" 6) Write Access Password")
    print(" 7) Lock Password Area")
    print(" 8) Full Tag Info (EPC + TID + Reserved)")
    print(" 9) Beep")
    print(" Q) Quit\n")


def pause():
    input("\nPress ENTER to continue...\n")


# ---------------------------------------------------------------------
# Main menu operations
# ---------------------------------------------------------------------

def op_detect_single(reader):
    try:
        epc = reader.require_single_tag()
        print(f"✓ Exactly one tag detected: {epc}")
        reader.beep()
    except Exception as e:
        print(f"✗ Error: {e}")


def op_read_epc(reader):
    try:
        epc = reader.read_epc()
        if epc:
            print(f"EPC: {epc}")
        else:
            print("No tag detected.")
    except Exception as e:
        print(f"Error: {e}")


def op_write_epc(reader):
    new_epc = input("Enter NEW EPC (hex): ").strip().upper()

    if len(new_epc) % 2 != 0:
        print("EPC must be even-length hex.")
        return

    try:
        epc = reader.require_single_tag()
        print("Tag:", epc)

        reader.write_epc(new_epc)
        print("✓ EPC updated.")
        reader.beep()
    except Exception as e:
        print(f"✗ Error: {e}")


def op_read_tid(reader):
    try:
        epc = reader.require_single_tag()
        tid = reader.read_tid()
        print("Tag:", epc)
        print("TID:", tid)
    except Exception as e:
        print(f"✗ Error: {e}")


def op_read_reserved(reader):
    try:
        epc = reader.require_single_tag()
        res = reader.read_reserved()
        print("Tag:", epc)
        print("Reserved bytes:", res.hex().upper())
        print("KillPwd:", res[0:4].hex().upper())
        print("AccessPwd:", res[4:8].hex().upper())
    except Exception as e:
        print(f"✗ Error: {e}")


def op_write_access_pwd(reader):
    newpwd_hex = input("Enter new 8-digit Access Password (hex): ").strip().upper()

    if len(newpwd_hex) != 8:
        print("Password must be exactly 8 hex digits.")
        return

    try:
        epc = reader.require_single_tag()
        print("Tag:", epc)

        reader.write_access_password(bytes.fromhex(newpwd_hex))
        print("✓ Access password updated.")
        reader.beep()
    except Exception as e:
        print(f"✗ Error: {e}")


def op_lock_password_area(reader):
    pwd_hex = input("Enter Access Password to authorize the lock (hex): ").strip().upper()
    if len(pwd_hex) != 8:
        print("Password must be 8 hex digits.")
        return

    pwd = bytes.fromhex(pwd_hex)

    print("\nLock choices:")
    print("1) Secured state only (normal)")
    print("2) Permanently locked (danger)")

    choice = input("Choice: ").strip()

    setprot = 0x02 if choice == "1" else 0x01

    try:
        epc = reader.require_single_tag()
        print("Tag:", epc)
        print("Locking password area...")

        reader.lock(select=0x01, setprotect=setprot, pwd=pwd)

        print("✓ Password area locked.")
        reader.beep()
    except Exception as e:
        print(f"✗ Error: {e}")


def op_full_info(reader):
    try:
        epc = reader.require_single_tag()
        tid = reader.read_tid()
        res = reader.read_reserved()

        print("Tag:", epc)
        print("TID:", tid)
        print("KillPwd:", res[0:4].hex().upper())
        print("AccessPwd:", res[4:8].hex().upper())

        reader.beep()
    except Exception as e:
        print(f"✗ Error: {e}")


def op_beep(reader):
    reader.beep(3, 1, 2)
    print("✓ Beep command sent.")


# ---------------------------------------------------------------------
# Main Program
# ---------------------------------------------------------------------

def main():
    banner()
    port = input("Enter COM port (e.g., COM3): ").strip() or "COM3"

    try:
        reader = GeeNFCReaderPro(port=port)
        print(f"Connected to reader on {port}.")
    except Exception as e:
        print(f"Failed to open reader: {e}")
        return

    while True:
        banner()
        menu()
        choice = input("Select: ").strip().upper()

        if choice == "1":
            op_detect_single(reader)
        elif choice == "2":
            op_read_epc(reader)
        elif choice == "3":
            op_write_epc(reader)
        elif choice == "4":
            op_read_tid(reader)
        elif choice == "5":
            op_read_reserved(reader)
        elif choice == "6":
            op_write_access_pwd(reader)
        elif choice == "7":
            op_lock_password_area(reader)
        elif choice == "8":
            op_full_info(reader)
        elif choice == "9":
            op_beep(reader)
        elif choice == "Q":
            print("Closing...")
            break
        else:
            print("Invalid choice.")

        pause()

    reader.close()
    print("Reader closed. Goodbye!")


if __name__ == "__main__":
    main()
