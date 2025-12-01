import random

def perform_raffle(participants):
    """
    Realizar sorteo aleatorio
    """
    if not participants:
        return None
    
    return random.choice(participants)