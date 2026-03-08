import torch
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Cache model in memory
_model = None
_alphabet = None
_batch_converter = None

def get_esm_model():
    global _model, _alphabet, _batch_converter
    if _model is None:
        import esm
        logger.info("Loading ESM-2 model (esm2_t33_650M_UR50D)...")
        result = esm.pretrained.esm2_t33_650M_UR50D()
        _model, _alphabet = result[0], result[1]
        _batch_converter = _alphabet.get_batch_converter()
        _model.eval()
        if torch.cuda.is_available():
            _model = _model.to('cuda:0')
        else:
            _model = _model.to('cpu')
    return _model, _alphabet, _batch_converter

def embed_sequences(sequences, batch_size=64):
    """
    Compute ESM-2 mean-pooled embeddings for a list of CDR3b sequences.
    """
    model, _, batch_converter = get_esm_model()
    device = next(model.parameters()).device
    
    all_embeddings = []
    n_batches = (len(sequences) + batch_size - 1) // batch_size
    
    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(sequences))
        batch_seqs = sequences[start:end]
        
        data = [(f"seq_{start + i}", seq) for i, seq in enumerate(batch_seqs)]
        _, _, batch_tokens = batch_converter(data)
        batch_tokens = batch_tokens.to(device)
        
        with torch.no_grad():
            results = model(batch_tokens, repr_layers=[33], return_contacts=False)
            
        representations = results["representations"][33]
        
        for i in range(len(batch_seqs)):
            seq_len = len(batch_seqs[i])
            seq_repr = representations[i, 1:seq_len + 1, :]
            mean_repr = seq_repr.mean(dim=0).cpu().numpy()
            all_embeddings.append(mean_repr)
            
    return np.array(all_embeddings)
