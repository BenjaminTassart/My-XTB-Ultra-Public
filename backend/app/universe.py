"""Sélection de départ, pas une composition d’indice ni un classement actuel."""
SECTORS = {
    'Technology': ('Technologie', 'AAPL MSFT NVDA ORCL ADBE'),
    'Communication Services': ('Communication', 'GOOGL META NFLX DIS CMCSA'),
    'Consumer Cyclical': ('Consommation discrétionnaire', 'AMZN TSLA HD MCD NKE'),
    'Consumer Defensive': ('Consommation courante', 'WMT COST PG KO PEP'),
    'Healthcare': ('Santé', 'LLY JNJ ABBV MRK UNH'),
    'Financial Services': ('Finance', 'JPM BAC WFC GS V'),
    'Industrials': ('Industrie', 'CAT GE HON UPS RTX'),
    'Energy': ('Énergie', 'XOM CVX COP SLB EOG'),
    'Basic Materials': ('Matériaux', 'LIN APD SHW FCX NEM'),
    'Real Estate': ('Immobilier', 'PLD AMT EQIX O PSA'),
    'Utilities': ('Services aux collectivités', 'NEE SO DUK AEP EXC'),
}
SYMBOLS = sorted({symbol for _, symbols in SECTORS.values() for symbol in symbols.split()})
