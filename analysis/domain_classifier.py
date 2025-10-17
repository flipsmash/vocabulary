#!/usr/bin/env python3
"""
Domain Classification System
Assigns hierarchical domain classifications to vocabulary terms based on:
1. Embedding-based clustering results
2. Keyword pattern matching  
3. Definition content analysis
4. Part-of-speech information
"""

import numpy as np
import mysql.connector
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.config import get_db_config
import json
import pickle
import re
from collections import defaultdict, Counter
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DomainClassifier:
    """Multi-domain hierarchical classifier for vocabulary terms"""
    
    def __init__(self, db_config):
        self.db_config = db_config
        self.domain_hierarchy = self._define_domain_hierarchy()
        self.keyword_patterns = self._define_keyword_patterns()
        self.cluster_mappings = {}
        
    def _define_domain_hierarchy(self):
        """Define hierarchical domain structure"""
        return {
            'Medical': {
                'Anatomical': ['relating to anatomy', 'body part', 'organ', 'tissue'],
                'Pathological': ['disease', 'condition', 'syndrome', 'disorder'],
                'Pharmacological': ['drug', 'medicine', 'treatment', 'therapy'],  
                'Physiological': ['function', 'process', 'mechanism', 'response']
            },
            'Scientific': {
                'Mathematical': ['number', 'equation', 'formula', 'calculation'],
                'Physical': ['force', 'energy', 'matter', 'physics'],
                'Chemical': ['compound', 'element', 'reaction', 'molecule'],
                'Biological': {
                    'Botanical': ['plant', 'tree', 'flower', 'leaf', 'seed'],
                    'Zoological': ['animal', 'species', 'mammal', 'bird', 'insect'],
                    'Ecological': ['environment', 'habitat', 'ecosystem', 'biodiversity']
                }
            },
            'Linguistic': {
                'Grammar': ['grammatical', 'syntax', 'morphology', 'phonology'],
                'Rhetoric': ['speech', 'persuasion', 'argument', 'discourse'],
                'Etymology': ['origin', 'derivation', 'historical', 'ancient']
            },
            'Historical': {
                'Archaic': ['obsolete', 'archaic', 'dated', 'old-fashioned'],
                'Classical': ['greek', 'roman', 'latin', 'classical'],
                'Religious': ['god', 'sacred', 'holy', 'spiritual', 'religious']
            },
            'Geographical': {
                'Physical': ['mountain', 'river', 'ocean', 'continent'],
                'Political': ['country', 'state', 'city', 'government'],
                'Cultural': ['tradition', 'custom', 'heritage', 'ethnicity']
            },
            'Arts': {
                'Literary': ['poem', 'story', 'novel', 'literature'],
                'Musical': ['music', 'instrument', 'melody', 'rhythm'],
                'Visual': ['art', 'painting', 'sculpture', 'design']
            }
        }
    
    def _define_keyword_patterns(self):
        """Define keyword patterns for domain identification"""
        return {
            # Medical patterns
            'Medical.Anatomical': [
                r'\b(anatomy|anatomical|bone|muscle|nerve|vessel|organ)\b',
                r'\b(cranial|spinal|cardiac|hepatic|renal|pulmonary)\b',
                r'\b(dorsal|ventral|lateral|medial|proximal|distal)\b',
                r'\b(anterior|posterior|superior|inferior)\b'
            ],
            'Medical.Pathological': [
                r'\b(disease|disorder|syndrome|condition|pathology)\b',
                r'\b(cancer|tumor|carcinoma|neoplasm|malignant)\b', 
                r'\b(infection|inflammation|itis|osis|pathy)\b',
                r'\b(acute|chronic|benign|metastatic)\b'
            ],
            'Medical.Pharmacological': [
                r'\b(drug|medicine|pharmaceutical|therapy|treatment)\b',
                r'\b(dose|dosage|administration|injection|oral)\b',
                r'\b(analgesic|antibiotic|antiviral|vaccine)\b'
            ],
            
            # Scientific patterns  
            'Scientific.Mathematical': [
                r'\b(mathematics|mathematical|equation|formula|theorem)\b',
                r'\b(algebra|geometry|calculus|statistics|probability)\b',
                r'\b(number|integer|fraction|decimal|ratio)\b'
            ],
            'Scientific.Physical': [
                r'\b(physics|physical|force|energy|motion|gravity)\b',
                r'\b(electromagnetic|thermal|optical|acoustic)\b',
                r'\b(atom|molecule|particle|quantum|relativity)\b'
            ],
            'Scientific.Biological.Botanical': [
                r'\b(plant|tree|flower|leaf|root|stem|seed|fruit)\b',
                r'\b(botany|botanical|flora|vegetation|photosynthesis)\b',
                r'\b(genus|species|family|order|classification)\b'
            ],
            'Scientific.Biological.Zoological': [
                r'\b(animal|mammal|bird|fish|insect|reptile|amphibian)\b',
                r'\b(zoology|zoological|fauna|species|habitat)\b',
                r'\b(carnivore|herbivore|omnivore|predator|prey)\b'
            ],
            
            # Linguistic patterns
            'Linguistic.Grammar': [
                r'\b(grammar|grammatical|syntax|morphology|phonology)\b',
                r'\b(noun|verb|adjective|adverb|pronoun|preposition)\b',
                r'\b(tense|case|declension|conjugation|inflection)\b'
            ],
            'Linguistic.Rhetoric': [
                r'\b(rhetoric|rhetorical|speech|oratory|persuasion)\b',
                r'\b(metaphor|simile|analogy|allegory|hyperbole)\b',
                r'\b(argument|discourse|debate|eloquence)\b'
            ],
            
            # Historical patterns
            'Historical.Archaic': [
                r'\b(archaic|obsolete|dated|antiquated|old-fashioned)\b',
                r'\b(formerly|erstwhile|bygone|ancient|medieval)\b'
            ],
            'Historical.Religious': [
                r'\b(god|divine|sacred|holy|spiritual|religious)\b',
                r'\b(church|temple|monastery|priest|bishop|saint)\b',
                r'\b(prayer|worship|ritual|ceremony|sacrament)\b',
                r'\b(christianity|judaism|islam|buddhism|hinduism)\b'
            ]
        }
    
    def load_cluster_results(self, cluster_file='domain_clusters.pkl'):
        """Load clustering results and create cluster-to-domain mappings"""
        logger.info(f"Loading cluster results from {cluster_file}")
        
        with open(cluster_file, 'rb') as f:
            results = pickle.load(f)
        
        self.clusters = results['clusters']
        self.words_data = results['words_data']
        
        # Analyze each cluster to determine likely domains
        self.cluster_mappings = self._analyze_clusters_for_domains()
        
        logger.info(f"Loaded {len(self.words_data)} words with cluster assignments")
    
    def _analyze_clusters_for_domains(self):
        """Analyze clusters to determine their primary domains"""
        cluster_mappings = {}
        unique_clusters = np.unique(self.clusters)
        
        for cluster_id in unique_clusters:
            cluster_mask = self.clusters == cluster_id
            cluster_words = [self.words_data[i] for i in range(len(self.words_data)) if cluster_mask[i]]
            
            # Count domain matches in this cluster
            domain_scores = defaultdict(int)
            
            for word_data in cluster_words:
                definition = word_data['definition']
                term = word_data['term']
                
                # Check against keyword patterns
                for domain, patterns in self.keyword_patterns.items():
                    for pattern in patterns:
                        if re.search(pattern, definition, re.IGNORECASE):
                            domain_scores[domain] += 1
                        if re.search(pattern, term, re.IGNORECASE):
                            domain_scores[domain] += 0.5  # Lower weight for term match
            
            # Determine primary domain(s) for this cluster
            if domain_scores:
                sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
                primary_domain = sorted_domains[0][0]
                
                # Include secondary domains if they have significant representation
                secondary_domains = [d for d, score in sorted_domains[1:3] 
                                   if score >= sorted_domains[0][1] * 0.3]
                
                cluster_mappings[cluster_id] = {
                    'primary': primary_domain,
                    'secondary': secondary_domains,
                    'scores': dict(domain_scores),
                    'size': len(cluster_words)
                }
            else:
                cluster_mappings[cluster_id] = {
                    'primary': 'General',
                    'secondary': [],
                    'scores': {},
                    'size': len(cluster_words)
                }
        
        return cluster_mappings
    
    def classify_word(self, word_data, cluster_id):
        """Classify a single word into domains"""
        term = word_data['term']
        definition = word_data['definition']
        pos = word_data.get('part_of_speech', '')
        
        # Start with cluster-based classification
        cluster_info = self.cluster_mappings.get(cluster_id, {})
        primary_domain = cluster_info.get('primary', 'General')
        secondary_domains = cluster_info.get('secondary', [])
        
        # Refine with individual word analysis
        word_domain_scores = defaultdict(float)
        
        # Check against all keyword patterns
        for domain, patterns in self.keyword_patterns.items():
            for pattern in patterns:
                if re.search(pattern, definition, re.IGNORECASE):
                    word_domain_scores[domain] += 1.0
                if re.search(pattern, term, re.IGNORECASE):
                    word_domain_scores[domain] += 0.5
        
        # Override cluster assignment if individual analysis is strong
        if word_domain_scores:
            best_individual = max(word_domain_scores.items(), key=lambda x: x[1])
            if best_individual[1] >= 2.0:  # Strong individual signal
                primary_domain = best_individual[0]
        
        # Collect all domains above threshold
        all_domains = []
        if primary_domain != 'General':
            all_domains.append(primary_domain)
        
        for domain, score in word_domain_scores.items():
            if score >= 1.0 and domain not in all_domains:
                all_domains.append(domain)
        
        # Add high-scoring secondary domains from cluster
        for domain in secondary_domains[:2]:  # Top 2 secondary
            if domain not in all_domains:
                all_domains.append(domain)
        
        return {
            'primary_domain': primary_domain,
            'all_domains': all_domains,
            'cluster_id': cluster_id,
            'confidence_scores': dict(word_domain_scores)
        }
    
    def create_domain_table(self):
        """Create database table for domain classifications"""
        logger.info("Creating domain classifications table")
        
        with mysql.connector.connect(**self.db_config) as conn:
            cursor = conn.cursor()
            
            # Create domains table
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS word_domains (
                word_id INT,
                term VARCHAR(255),
                primary_domain VARCHAR(100),
                all_domains JSON,
                cluster_id INT,
                confidence_scores JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_word_id (word_id),
                INDEX idx_primary_domain (primary_domain),
                INDEX idx_cluster_id (cluster_id)
            )
            """
            
            cursor.execute(create_table_sql)
            
            # Clear existing data
            cursor.execute("DELETE FROM vocab.word_domains")
            conn.commit()
            
            logger.info("Domain table created successfully")
    
    def classify_all_words(self):
        """Classify all words and store results"""
        logger.info("Classifying all words into domains")
        
        classifications = []
        
        for i, word_data in enumerate(self.words_data):
            cluster_id = int(self.clusters[i])
            classification = self.classify_word(word_data, cluster_id)
            
            classifications.append({
                'word_id': word_data['word_id'],
                'term': word_data['term'],
                'primary_domain': classification['primary_domain'],
                'all_domains': classification['all_domains'],
                'cluster_id': cluster_id,
                'confidence_scores': classification['confidence_scores']
            })
        
        # Store in database
        self._store_classifications(classifications)
        
        return classifications
    
    def _store_classifications(self, classifications):
        """Store domain classifications in database"""
        logger.info(f"Storing {len(classifications)} domain classifications")
        
        with mysql.connector.connect(**self.db_config) as conn:
            cursor = conn.cursor()
            
            insert_sql = """
            INSERT INTO vocab.word_domains 
            (word_id, term, primary_domain, all_domains, cluster_id, confidence_scores)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            batch_data = []
            for c in classifications:
                batch_data.append((
                    c['word_id'],
                    c['term'],
                    c['primary_domain'],
                    json.dumps(c['all_domains']),
                    c['cluster_id'],
                    json.dumps(c['confidence_scores'])
                ))
            
            cursor.executemany(insert_sql, batch_data)
            conn.commit()
            
            logger.info("Domain classifications stored successfully")
    
    def analyze_domain_distribution(self):
        """Analyze and report domain distribution"""
        logger.info("Analyzing domain distribution")
        
        with mysql.connector.connect(**self.db_config) as conn:
            cursor = conn.cursor()
            
            # Primary domain distribution
            cursor.execute("""
                SELECT primary_domain, COUNT(*) as count 
                FROM vocab.word_domains 
                GROUP BY primary_domain 
                ORDER BY count DESC
            """)
            
            primary_dist = cursor.fetchall()
            
            print("\n" + "="*60)
            print("DOMAIN CLASSIFICATION RESULTS")
            print("="*60)
            
            print(f"\nPrimary Domain Distribution:")
            print("-" * 40)
            total_words = sum(count for _, count in primary_dist)
            
            for domain, count in primary_dist:
                percentage = (count / total_words) * 100
                print(f"{domain:25s}: {count:4d} ({percentage:5.1f}%)")
            
            # Sample words from major domains
            for domain, count in primary_dist[:8]:  # Top 8 domains
                cursor.execute("""
                    SELECT term FROM vocab.word_domains 
                    WHERE primary_domain = %s 
                    ORDER BY RAND() 
                    LIMIT 8
                """, (domain,))
                
                samples = [row[0] for row in cursor.fetchall()]
                print(f"\n{domain} examples: {', '.join(samples)}")
    
    def print_cluster_domain_mappings(self):
        """Print cluster to domain mappings"""
        print(f"\n{'='*60}")
        print("CLUSTER TO DOMAIN MAPPINGS")
        print("="*60)
        
        sorted_clusters = sorted(self.cluster_mappings.items(), 
                               key=lambda x: x[1]['size'], reverse=True)
        
        for cluster_id, info in sorted_clusters[:15]:  # Top 15 clusters
            print(f"\nCluster {cluster_id} ({info['size']} words)")
            print(f"  Primary: {info['primary']}")
            if info['secondary']:
                print(f"  Secondary: {', '.join(info['secondary'])}")
            
            # Show top scoring domains
            if info['scores']:
                top_scores = sorted(info['scores'].items(), key=lambda x: x[1], reverse=True)[:3]
                score_str = ", ".join([f"{d}: {s}" for d, s in top_scores])
                print(f"  Scores: {score_str}")

def main():
    """Main classification function"""
    print("Domain Classification System")
    print("=" * 50)
    
    classifier = DomainClassifier(get_db_config())
    
    # Load clustering results
    classifier.load_cluster_results()
    
    # Print cluster mappings
    classifier.print_cluster_domain_mappings()
    
    # Create database table
    classifier.create_domain_table()
    
    # Classify all words
    classifications = classifier.classify_all_words()
    
    # Analyze results
    classifier.analyze_domain_distribution()
    
    print(f"\n✅ Domain classification complete!")
    print(f"Classified {len(classifications)} words into hierarchical domains")
    print("Results stored in 'word_domains' table")

if __name__ == "__main__":
    main()