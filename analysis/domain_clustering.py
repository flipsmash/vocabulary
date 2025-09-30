#!/usr/bin/env python3
"""
Domain Clustering Analysis
Uses existing definition embeddings to discover natural semantic domains through clustering
"""

import numpy as np
import mysql.connector
from config import get_db_config
from sklearn.cluster import KMeans, DBSCAN
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
import pickle
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DomainClusterAnalyzer:
    """Analyze definition embeddings to discover semantic domains"""
    
    def __init__(self, db_config):
        self.db_config = db_config
        self.embeddings = None
        self.words_data = None
        self.clusters = None
        
    def load_embeddings_and_words(self):
        """Load embeddings and corresponding word information"""
        logger.info("Loading embeddings and word data from database...")
        
        with mysql.connector.connect(**self.db_config) as conn:
            cursor = conn.cursor()
            
            # Get embeddings with word information
            query = """
            SELECT 
                e.word_id,
                e.embedding_json,
                d.term,
                d.definition,
                d.part_of_speech,
                d.frequency
            FROM definition_embeddings e
            JOIN defined d ON e.word_id = d.id
            ORDER BY e.word_id
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            logger.info(f"Loaded {len(results)} word embeddings")
            
            # Parse embeddings and collect word data
            embeddings = []
            words_data = []
            
            for word_id, embedding_json, term, definition, pos, frequency in results:
                # Convert JSON to numpy array
                import json
                embedding = np.array(json.loads(embedding_json), dtype=np.float32)
                embeddings.append(embedding)
                
                words_data.append({
                    'word_id': word_id,
                    'term': term,
                    'definition': definition,
                    'part_of_speech': pos,
                    'frequency': frequency
                })
            
            self.embeddings = np.array(embeddings)
            self.words_data = words_data
            
            logger.info(f"Processed embeddings shape: {self.embeddings.shape}")
            
    def analyze_optimal_clusters(self, max_k=50, sample_size=5000):
        """Use elbow method to find optimal number of clusters"""
        logger.info("Analyzing optimal number of clusters...")
        
        # Use sample for faster computation
        if len(self.embeddings) > sample_size:
            indices = np.random.choice(len(self.embeddings), sample_size, replace=False)
            sample_embeddings = self.embeddings[indices]
        else:
            sample_embeddings = self.embeddings
            
        # Standardize embeddings
        scaler = StandardScaler()
        sample_embeddings_scaled = scaler.fit_transform(sample_embeddings)
        
        inertias = []
        k_range = range(5, min(max_k, len(sample_embeddings) // 10))
        
        for k in k_range:
            logger.info(f"Testing k={k} clusters...")
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            kmeans.fit(sample_embeddings_scaled)
            inertias.append(kmeans.inertia_)
        
        # Find elbow point (simple method)
        elbow_scores = []
        for i in range(1, len(inertias) - 1):
            score = inertias[i-1] - 2*inertias[i] + inertias[i+1]
            elbow_scores.append(score)
        
        optimal_k = k_range[np.argmax(elbow_scores) + 1]
        
        logger.info(f"Optimal number of clusters: {optimal_k}")
        
        # Plot elbow curve
        plt.figure(figsize=(10, 6))
        plt.plot(k_range, inertias, 'bo-')
        plt.axvline(x=optimal_k, color='red', linestyle='--', label=f'Optimal k={optimal_k}')
        plt.xlabel('Number of Clusters (k)')
        plt.ylabel('Inertia')
        plt.title('Elbow Method for Optimal k')
        plt.legend()
        plt.grid(True)
        plt.savefig('cluster_elbow.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        return optimal_k
        
    def perform_clustering(self, n_clusters=None, use_dbscan=False):
        """Perform clustering on embeddings"""
        logger.info("Performing clustering analysis...")
        
        # Standardize embeddings
        scaler = StandardScaler()
        embeddings_scaled = scaler.fit_transform(self.embeddings)
        
        if use_dbscan:
            logger.info("Using DBSCAN clustering...")
            # DBSCAN - density-based clustering
            clusterer = DBSCAN(eps=0.5, min_samples=5, metric='cosine')
            cluster_labels = clusterer.fit_predict(embeddings_scaled)
        else:
            if n_clusters is None:
                n_clusters = self.analyze_optimal_clusters()
            
            logger.info(f"Using K-Means clustering with {n_clusters} clusters...")
            clusterer = KMeans(n_clusters=n_clusters, random_state=42, n_init=20)
            cluster_labels = clusterer.fit_predict(embeddings_scaled)
        
        self.clusters = cluster_labels
        
        # Analyze cluster distribution
        cluster_counts = Counter(cluster_labels)
        logger.info(f"Cluster distribution: {dict(cluster_counts)}")
        
        return cluster_labels
        
    def analyze_clusters(self, top_words_per_cluster=20):
        """Analyze and interpret each cluster"""
        logger.info("Analyzing cluster characteristics...")
        
        unique_clusters = np.unique(self.clusters)
        cluster_analysis = {}
        
        for cluster_id in unique_clusters:
            if cluster_id == -1:  # DBSCAN noise
                continue
                
            # Get words in this cluster
            cluster_mask = self.clusters == cluster_id
            cluster_words = [self.words_data[i] for i in range(len(self.words_data)) if cluster_mask[i]]
            
            # Sort by frequency (if available) or alphabetically
            cluster_words.sort(key=lambda x: x['frequency'] if x['frequency'] else 0, reverse=True)
            
            # Extract common patterns
            definitions = [word['definition'] for word in cluster_words[:100]]  # Top 100 for analysis
            terms = [word['term'] for word in cluster_words]
            pos_tags = [word['part_of_speech'] for word in cluster_words if word['part_of_speech']]
            
            # Analyze part of speech distribution
            pos_counter = Counter(pos_tags)
            
            # Sample words for manual inspection
            sample_words = cluster_words[:top_words_per_cluster]
            
            cluster_analysis[cluster_id] = {
                'size': len(cluster_words),
                'sample_words': sample_words,
                'pos_distribution': dict(pos_counter),
                'avg_frequency': np.mean([w['frequency'] for w in cluster_words if w['frequency']]),
            }
            
        return cluster_analysis
        
    def visualize_clusters(self, n_components=2, sample_size=2000):
        """Create 2D visualization of clusters using PCA"""
        logger.info("Creating cluster visualization...")
        
        # Sample for visualization if dataset is large
        if len(self.embeddings) > sample_size:
            indices = np.random.choice(len(self.embeddings), sample_size, replace=False)
            sample_embeddings = self.embeddings[indices]
            sample_clusters = self.clusters[indices]
            sample_words = [self.words_data[i]['term'] for i in indices]
        else:
            sample_embeddings = self.embeddings
            sample_clusters = self.clusters
            sample_words = [w['term'] for w in self.words_data]
        
        # Reduce dimensionality for visualization
        pca = PCA(n_components=n_components, random_state=42)
        embeddings_2d = pca.fit_transform(sample_embeddings)
        
        # Create scatter plot
        plt.figure(figsize=(15, 12))
        
        unique_clusters = np.unique(sample_clusters)
        colors = plt.cm.Set3(np.linspace(0, 1, len(unique_clusters)))
        
        for i, cluster_id in enumerate(unique_clusters):
            if cluster_id == -1:  # Noise points
                color = 'black'
                alpha = 0.3
                s = 10
            else:
                color = colors[i]
                alpha = 0.6
                s = 30
                
            mask = sample_clusters == cluster_id
            plt.scatter(embeddings_2d[mask, 0], embeddings_2d[mask, 1], 
                       c=[color], alpha=alpha, s=s, label=f'Cluster {cluster_id}')
        
        plt.xlabel(f'PC1 (explains {pca.explained_variance_ratio_[0]:.1%} variance)')
        plt.ylabel(f'PC2 (explains {pca.explained_variance_ratio_[1]:.1%} variance)')
        plt.title('Word Clusters in 2D Semantic Space')
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig('clusters_visualization.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Visualization saved as 'clusters_visualization.png'")
        logger.info(f"PC1 explains {pca.explained_variance_ratio_[0]:.1%} of variance")
        logger.info(f"PC2 explains {pca.explained_variance_ratio_[1]:.1%} of variance")
        
    def save_cluster_results(self, filename='domain_clusters.pkl'):
        """Save clustering results for later analysis"""
        results = {
            'clusters': self.clusters,
            'words_data': self.words_data,
            'embeddings_shape': self.embeddings.shape
        }
        
        with open(filename, 'wb') as f:
            pickle.dump(results, f)
            
        logger.info(f"Results saved to {filename}")
        
    def print_cluster_report(self, cluster_analysis, max_clusters_to_show=15):
        """Print a detailed report of cluster findings"""
        print("\n" + "="*80)
        print("DOMAIN CLUSTERING ANALYSIS REPORT")
        print("="*80)
        
        sorted_clusters = sorted(cluster_analysis.items(), 
                               key=lambda x: x[1]['size'], reverse=True)
        
        for i, (cluster_id, analysis) in enumerate(sorted_clusters[:max_clusters_to_show]):
            print(f"\nCLUSTER {cluster_id} ({analysis['size']} words)")
            print("-" * 50)
            
            # Show top parts of speech
            if analysis['pos_distribution']:
                top_pos = sorted(analysis['pos_distribution'].items(), 
                               key=lambda x: x[1], reverse=True)[:3]
                pos_str = ", ".join([f"{pos}: {count}" for pos, count in top_pos])
                print(f"Top POS: {pos_str}")
            
            if analysis['avg_frequency']:
                print(f"Avg Frequency: {analysis['avg_frequency']:.3f}")
            
            print("Sample words:")
            for j, word in enumerate(analysis['sample_words'][:12]):
                definition = word['definition'][:60] + "..." if len(word['definition']) > 60 else word['definition']
                print(f"  {j+1:2d}. {word['term']:15s} - {definition}")
                
        print(f"\n... showing top {min(max_clusters_to_show, len(sorted_clusters))} clusters out of {len(sorted_clusters)} total")

def main():
    """Main analysis function"""
    print("Domain Clustering Analysis")
    print("=" * 50)
    
    analyzer = DomainClusterAnalyzer(get_db_config())
    
    # Load data
    analyzer.load_embeddings_and_words()
    
    # Perform clustering
    start_time = time.time()
    cluster_labels = analyzer.perform_clustering(n_clusters=25)  # Start with 25 clusters
    clustering_time = time.time() - start_time
    
    print(f"Clustering completed in {clustering_time:.1f} seconds")
    
    # Analyze results
    cluster_analysis = analyzer.analyze_clusters()
    
    # Print report
    analyzer.print_cluster_report(cluster_analysis)
    
    # Create visualizations
    analyzer.visualize_clusters()
    
    # Save results
    analyzer.save_cluster_results()
    
    print(f"\nAnalysis complete! Check cluster_elbow.png and clusters_visualization.png")
    print("Results saved to domain_clusters.pkl for further analysis")

if __name__ == "__main__":
    main()