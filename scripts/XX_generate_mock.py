import numpy as np, pandas as pd, json
from pathlib import Path
from ..server.data.loaders import load_tcr_db_from_npz
from ..server.core.config import settings

print('Generating realistic mock predictions...')
tcrs = load_tcr_db_from_npz(settings.embed_dir / 'esm2_cdr3b_embeddings.npz')
heroes = tcrs.head(100).copy()

EPITOPES = [
  ('MART1_ELAGIGILTV', 'melanocyte', 'MLANA/MART-1'),
  ('gp100_KTWGQYWQV', 'melanocyte', 'PMEL/gp100'),
  ('TRP2_SVYDFFVWL', 'melanocyte', 'DCT/TRP-2'),
  ('NYESO1_SLLMWITQC', 'cancer', 'NY-ESO-1'),
  ('CMV_NLVPMVATV', 'viral', 'pp65/CMV'),
  ('EBV_GLCTLVAML', 'viral', 'BMLF1/EBV'),
  ('FLU_GILGFVFTL', 'viral', 'M1/Influenza'),
  ('COVID_YLQPRTFLL', 'viral', 'Spike/SARS-CoV-2')
]

rows = []
for _, row in heroes.iterrows():
    base_score = np.random.normal(-0.5, 0.2)
    for ep_name, cat, gene in EPITOPES:
        bias = 0.2 if cat == 'viral' else 0
        if cat == 'melanocyte' and ep_name.startswith('TRP2') and row['source'] == 'TCRAFT':
            bias = 0.4
            
        score = base_score + bias + np.random.normal(0, 0.15)
        rows.append({
            'tcr_id': row['tcr_id'],
            'epitope_name': ep_name,
            'epitope_category': cat,
            'epitope_gene': gene,
            'interaction_score': score
        })

df = pd.DataFrame(rows)
out_dir = settings.pred_dir
out_dir.mkdir(parents=True, exist_ok=True)

df.to_csv(out_dir / 'decoder_tcr_scores_long.csv', index=False)
print(f'Saved {len(df)} mocked prediction scores.')

print('Generating mock mutagenesis for hero TCRAFT_0001...')
mut_dir = out_dir / 'mutagenesis'
mut_dir.mkdir(exist_ok=True)

hero_id = 'TCRAFT_0001'
cdr3b = tcrs[tcrs['tcr_id'] == hero_id]['CDR3b'].iloc[0]

aas = list('ACDEFGHIKLMNPQRSTVWY')
landscape = []
for i, wt in enumerate(cdr3b):
    for mut in aas:
        if mut == wt: continue
        delta = np.random.normal(0, 0.05) if i < 3 or i > len(cdr3b)-3 else np.random.normal(-0.2, 0.3)
        landscape.append({
            'position': i, 'wt_aa': wt, 'mut_aa': mut, 'delta': round(delta, 3)
        })

mut_data = {
  'tcr_id': hero_id,
  'epitope': 'TRP2_SVYDFFVWL',
  'wild_type_score': -0.32,
  'cdr3b': cdr3b,
  'landscape': landscape,
  'top_variants': [
      {'mutations': f'{cdr3b[5]}5W', 'predicted_score': -0.08, 'delta': 0.24, 'note': 'Hypothesis — requires experimental validation'}
  ]
}

with open(mut_dir / f'{hero_id}.json', 'w') as f:
    json.dump(mut_data, f)
print(f'Saved mutagenesis for {hero_id} ({len(landscape)} variants).')
