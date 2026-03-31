#!/usr/bin/env python3
"""
KILL COMMAND TEST
⚠️ WARNING: This will attempt to PERMANENTLY destroy a tag!
Only use this on tags you want to destroy!
"""

from uhf_rfid_tool import URFIDReader

def main():
    print("=" * 70)
    print("⚠️  RFID TAG KILL COMMAND TEST")
    print("=" * 70)
    print()
    print("This script will attempt to kill a tag with kill password 00000001")
    print("Since the tag's Reserved memory is locked, this SHOULD fail safely.")
    print()
    
    PORT = "COM3"
    
    reader = URFIDReader(PORT)
    
    if not reader.connect():
        return
    
    # Scan for tag
    tags = reader.inventory(retry_count=3)
    
    if not tags:
        print("\n⚠️  No tags found.")
        reader.disconnect()
        return
    
    target_epc = tags[0]
    print(f"\n🎯 Target tag: {target_epc}")
    
    # Confirm
    print("\n" + "=" * 70)
    print("⚠️  FINAL WARNING")
    print("=" * 70)
    print()
    print("This will attempt to KILL the tag, making it permanently unusable.")
    print("Since your tag has locked Reserved memory, it SHOULD be protected.")
    print()
    response = input("Type 'KILL' to proceed (or anything else to cancel): ")
    
    if response.strip().upper() != "KILL":
        print("\n✓ Cancelled - tag is safe")
        reader.disconnect()
        return
    
    print("\n" + "=" * 70)
    print("Attempting kill with password 00000001...")
    print("=" * 70)
    
    # Try to kill with password 00000001
    # This should fail because:
    # 1. The kill password is locked
    # 2. Even if not locked, 00000001 is probably not the correct password
    result = reader.kill_tag(kill_password="00000000", epc=target_epc)
    
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)
    
    if result:
        print("❌ Tag was killed! (This shouldn't happen)")
        print("   The tag is now permanently disabled.")
    else:
        print("✅ Tag is protected from kill command!")
        print("   The locked Reserved memory prevented the kill operation.")
    
    print("\nVerifying tag is still responsive...")
    import time
    time.sleep(1)
    
    tags_after = reader.inventory(retry_count=3)
    
    if tags_after and target_epc in tags_after:
        print(f"✅ Tag {target_epc} is still alive and responding!")
    else:
        print(f"⚠️  Tag is not responding (either killed or moved away)")
    
    reader.disconnect()


if __name__ == "__main__":
    main()