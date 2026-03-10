use regex::Regex;
use std::sync::LazyLock;

static TOKEN_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[^a-z0-9_#\-\s]").unwrap());

/// Tokenize a string for BM25 scoring: lowercase, strip non-alpha, filter len>1.
pub fn tokenize(s: &str) -> Vec<String> {
    let lower = s.to_lowercase();
    let cleaned = TOKEN_RE.replace_all(&lower, " ");
    cleaned
        .split_whitespace()
        .filter(|t| t.len() > 1)
        .map(|t| t.to_string())
        .collect()
}

/// BM25-Okapi scoring engine operating on a pre-built inverted index.
pub struct Bm25Index {
    /// Number of documents.
    n_docs: usize,
    /// Average document length in tokens.
    avgdl: f64,
    /// Per-document token count.
    doc_lens: Vec<usize>,
    /// Inverted index: term → Vec<(doc_id, term_frequency)>.
    postings: std::collections::HashMap<String, Vec<(usize, u32)>>,
    /// IDF cache: term → idf value.
    idf_cache: std::collections::HashMap<String, f64>,
}

impl Bm25Index {
    const K1: f64 = 1.5;
    const B: f64 = 0.75;

    /// Build BM25 index from a corpus of pre-tokenized documents.
    pub fn new(corpus: &[Vec<String>]) -> Self {
        let n_docs = corpus.len();
        let doc_lens: Vec<usize> = corpus.iter().map(|doc| doc.len()).collect();
        let total_len: usize = doc_lens.iter().sum();
        let avgdl = if n_docs > 0 {
            total_len as f64 / n_docs as f64
        } else {
            1.0
        };

        // Build inverted index
        let mut postings: std::collections::HashMap<String, Vec<(usize, u32)>> =
            std::collections::HashMap::new();
        for (doc_id, doc) in corpus.iter().enumerate() {
            let mut tf: std::collections::HashMap<&str, u32> = std::collections::HashMap::new();
            for token in doc {
                *tf.entry(token.as_str()).or_default() += 1;
            }
            for (term, freq) in tf {
                postings
                    .entry(term.to_string())
                    .or_default()
                    .push((doc_id, freq));
            }
        }

        // Pre-compute IDF for all terms
        let mut idf_cache = std::collections::HashMap::new();
        for (term, posting_list) in &postings {
            let df = posting_list.len() as f64;
            let idf = ((n_docs as f64 - df + 0.5) / (df + 0.5) + 1.0).ln();
            idf_cache.insert(term.clone(), idf);
        }

        Bm25Index {
            n_docs,
            avgdl,
            doc_lens,
            postings,
            idf_cache,
        }
    }

    /// Score all documents against query tokens, return top-k (doc_index, score) sorted desc.
    pub fn query(&self, tokens: &[String], k: usize) -> Vec<(usize, f64)> {
        if tokens.is_empty() || self.n_docs == 0 {
            return Vec::new();
        }

        // Only score documents that contain at least one query term (skip-list style)
        let mut scores: std::collections::HashMap<usize, f64> = std::collections::HashMap::new();

        for token in tokens {
            let idf = match self.idf_cache.get(token.as_str()) {
                Some(&v) => v,
                None => continue,
            };
            let posting_list = match self.postings.get(token.as_str()) {
                Some(v) => v,
                None => continue,
            };

            for &(doc_id, tf) in posting_list {
                let dl = self.doc_lens[doc_id] as f64;
                let tf_f = tf as f64;
                let numerator = tf_f * (Self::K1 + 1.0);
                let denominator = tf_f + Self::K1 * (1.0 - Self::B + Self::B * dl / self.avgdl);
                let score = idf * numerator / denominator;
                *scores.entry(doc_id).or_default() += score;
            }
        }

        // Partial sort for top-k using a min-heap would be optimal,
        // but for ~4k docs a full sort is fast enough (<1ms).
        let mut scored: Vec<(usize, f64)> = scores.into_iter().collect();
        scored.sort_unstable_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(k);
        scored
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tokenize_basic() {
        let tokens = tokenize("BaseModel validation");
        assert!(tokens.contains(&"basemodel".to_string()));
        assert!(tokens.contains(&"validation".to_string()));
    }

    #[test]
    fn test_tokenize_filters_short() {
        let tokens = tokenize("a bb ccc d");
        assert!(!tokens.contains(&"a".to_string()));
        assert!(!tokens.contains(&"d".to_string()));
        assert!(tokens.contains(&"bb".to_string()));
        assert!(tokens.contains(&"ccc".to_string()));
    }

    #[test]
    fn test_tokenize_case_insensitive() {
        let t1 = tokenize("BaseModel VALIDATION");
        let t2 = tokenize("basemodel validation");
        assert_eq!(t1, t2);
    }

    #[test]
    fn test_tokenize_preserves_special() {
        let tokens = tokenize("test-value_name #tag");
        assert!(tokens.iter().any(|t| t.contains('-') || t.contains('_') || t.contains('#')));
    }

    #[test]
    fn test_bm25_basic() {
        let corpus = vec![
            tokenize("pydantic basemodel validation"),
            tokenize("python typing annotations"),
            tokenize("pydantic field types validation"),
        ];
        let index = Bm25Index::new(&corpus);
        let results = index.query(&tokenize("pydantic validation"), 10);
        assert!(!results.is_empty());
        // Docs 0 and 2 mention both terms, should rank higher
        let top_id = results[0].0;
        assert!(top_id == 0 || top_id == 2);
    }

    #[test]
    fn test_bm25_empty_query() {
        let corpus = vec![tokenize("some document")];
        let index = Bm25Index::new(&corpus);
        let results = index.query(&[], 10);
        assert!(results.is_empty());
    }

    #[test]
    fn test_bm25_no_match() {
        let corpus = vec![tokenize("pydantic basemodel")];
        let index = Bm25Index::new(&corpus);
        let results = index.query(&tokenize("completely unrelated xyz"), 10);
        assert!(results.is_empty());
    }
}
