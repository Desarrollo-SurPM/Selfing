import os
from core.scheduler import start

# Prevenir que el scheduler se inicie dos veces
if __name__ == '__main__':
    print("Iniciando proceso de worker del scheduler...")
    start()

# Mantener el proceso vivo para que el scheduler siga corriendo
import time
while True:
    time.sleep(1)