"""Self-generated modular arithmetic practice fixture; no real contest data."""
import json
from pathlib import Path

data = json.loads(Path('input.json').read_text())
inverse = pow(data['multiplier'], -1, data['modulus'])
print(''.join(chr((value - data['offset']) * inverse % data['modulus'])
              for value in data['encoded']))
