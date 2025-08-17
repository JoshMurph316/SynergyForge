import argparse, time
def main():
  p = argparse.ArgumentParser()
  p.add_argument("--testing", type=int, default=None)
  args = p.parse_args()
  print("SynergyForge pipeline starting…")
  print("Testing mode:" if args.testing else "Full mode:")
  time.sleep(1)
  print("SynergyForge pipeline finished ✓")
if __name__ == "__main__":
  main()