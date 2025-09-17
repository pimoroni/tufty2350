import cppmem
# Switch C++ memory allocations to use MicroPython's heap
cppmem.set_mode(cppmem.MICROPYTHON)

try:
    with open("state/hardware_test.txt", "r"):
        import hardware_test   # noqa F401
except OSError:
    pass
