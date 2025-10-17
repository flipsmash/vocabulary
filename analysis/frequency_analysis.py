#!/usr/bin/env python3
"""
Frequency Analysis of Vocabulary Database
Analyzes word frequency distributions to identify rare, common, and interesting patterns
"""

import mysql.connector
from config import get_db_config
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from collections import Counter, defaultdict
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FrequencyAnalyzer:
    """Comprehensive frequency analysis for vocabulary database"""
    
    def __init__(self, db_config):
        self.db_config = db_config
        self.words_df = None
        
    def load_vocabulary_data(self):
        """Load complete vocabulary dataset with all relevant fields"""
        logger.info("Loading vocabulary data from database...")
        
        with mysql.connector.connect(**self.db_config) as conn:
            # Get complete word data with domains if available
            query = """
            SELECT 
                d.id,
                d.term,
                d.definition,
                d.part_of_speech,
                d.frequency,
                d.len as term_length,
                d.quizzed,
                d.correct2,
                d.date_added,
                wd.primary_domain,
                wd.all_domains
            FROM vocab.defined d
            LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
            ORDER BY d.frequency DESC
            """
            
            self.words_df = pd.read_sql(query, conn)
            
        logger.info(f"Loaded {len(self.words_df)} vocabulary terms")
        
        # Clean and process data
        self.words_df['frequency'] = pd.to_numeric(self.words_df['frequency'], errors='coerce').fillna(0)
        self.words_df['term_length'] = pd.to_numeric(self.words_df['term_length'], errors='coerce').fillna(0)
        
        # Parse domain data
        self.words_df['all_domains_list'] = self.words_df['all_domains'].apply(
            lambda x: json.loads(x) if x and x != 'null' else []
        )
        
        return self.words_df
    
    def basic_frequency_statistics(self):
        """Calculate basic frequency distribution statistics"""
        logger.info("Calculating frequency statistics...")
        
        freq_data = self.words_df['frequency']
        non_zero_freq = freq_data[freq_data > 0]
        
        stats = {
            'total_words': len(self.words_df),
            'words_with_frequency': len(non_zero_freq),
            'zero_frequency_words': len(freq_data[freq_data == 0]),
            'mean_frequency': float(freq_data.mean()),
            'median_frequency': float(freq_data.median()),
            'std_frequency': float(freq_data.std()),
            'min_frequency': float(freq_data.min()),
            'max_frequency': float(freq_data.max()),
            'percentiles': {
                '1st': float(freq_data.quantile(0.01)),
                '5th': float(freq_data.quantile(0.05)),
                '10th': float(freq_data.quantile(0.10)),
                '25th': float(freq_data.quantile(0.25)),
                '75th': float(freq_data.quantile(0.75)),
                '90th': float(freq_data.quantile(0.90)),
                '95th': float(freq_data.quantile(0.95)),
                '99th': float(freq_data.quantile(0.99))
            }
        }
        
        return stats
    
    def rarity_classification(self):
        """Classify words by rarity levels"""
        logger.info("Classifying words by rarity...")
        
        # Define rarity thresholds based on frequency distribution
        freq_data = self.words_df['frequency']
        
        # Calculate thresholds
        p1 = freq_data.quantile(0.01)   # Ultra-rare: bottom 1%
        p5 = freq_data.quantile(0.05)   # Very rare: bottom 5% 
        p10 = freq_data.quantile(0.10)  # Rare: bottom 10%
        p25 = freq_data.quantile(0.25)  # Uncommon: bottom 25%
        p75 = freq_data.quantile(0.75)  # Common: top 25%
        p95 = freq_data.quantile(0.95)  # Very common: top 5%
        
        def classify_rarity(freq):
            if freq == 0:
                return 'No Data'
            elif freq <= p1:
                return 'Ultra-Rare'
            elif freq <= p5:
                return 'Very Rare'
            elif freq <= p10:
                return 'Rare'
            elif freq <= p25:
                return 'Uncommon'
            elif freq <= p75:
                return 'Moderate'
            elif freq <= p95:
                return 'Common'
            else:
                return 'Very Common'
        
        self.words_df['rarity_class'] = self.words_df['frequency'].apply(classify_rarity)
        
        # Count distribution
        rarity_dist = self.words_df['rarity_class'].value_counts()
        
        return dict(rarity_dist), {
            'ultra_rare_threshold': p1,
            'very_rare_threshold': p5,
            'rare_threshold': p10,
            'uncommon_threshold': p25,
            'common_threshold': p75,
            'very_common_threshold': p95
        }
    
    def analyze_by_domain(self):
        """Analyze frequency patterns by domain"""
        logger.info("Analyzing frequency by domain...")
        
        domain_stats = {}
        
        # Primary domain analysis
        if 'primary_domain' in self.words_df.columns:
            domain_groups = self.words_df.groupby('primary_domain')['frequency']
            
            for domain, freq_series in domain_groups:
                if pd.isna(domain):
                    domain = 'Unclassified'
                    
                domain_stats[domain] = {
                    'count': len(freq_series),
                    'mean_frequency': float(freq_series.mean()),
                    'median_frequency': float(freq_series.median()),
                    'std_frequency': float(freq_series.std()),
                    'min_frequency': float(freq_series.min()),
                    'max_frequency': float(freq_series.max())
                }
        
        return domain_stats
    
    def analyze_by_length(self):
        """Analyze frequency patterns by word length"""
        logger.info("Analyzing frequency by word length...")
        
        length_stats = {}
        length_groups = self.words_df.groupby('term_length')['frequency']
        
        for length, freq_series in length_groups:
            if pd.isna(length) or length == 0:
                continue
                
            length_stats[int(length)] = {
                'count': len(freq_series),
                'mean_frequency': float(freq_series.mean()),
                'median_frequency': float(freq_series.median()),
                'rare_words_count': len(freq_series[freq_series <= freq_series.quantile(0.10)])
            }
        
        return length_stats
    
    def find_interesting_outliers(self):
        """Find statistically interesting words (outliers)"""
        logger.info("Finding interesting outliers...")
        
        outliers = {
            'ultra_rare_gems': [],
            'surprisingly_common': [],
            'long_rare_words': [],
            'short_rare_words': [],
            'domain_outliers': []
        }
        
        freq_data = self.words_df['frequency']
        
        # Ultra-rare gems (bottom 0.1% with interesting characteristics)
        ultra_rare = self.words_df[freq_data <= freq_data.quantile(0.001)]
        ultra_rare_sorted = ultra_rare.sort_values('frequency')
        outliers['ultra_rare_gems'] = ultra_rare_sorted.head(50)[['term', 'definition', 'frequency', 'primary_domain']].to_dict('records')
        
        # Surprisingly common words that seem rare
        # Words with "archaic", "obsolete" in definition but high frequency
        archaic_mask = self.words_df['definition'].str.contains('archaic|obsolete|dated', case=False, na=False)
        surprisingly_common = self.words_df[archaic_mask & (freq_data >= freq_data.quantile(0.80))]
        outliers['surprisingly_common'] = surprisingly_common.head(20)[['term', 'definition', 'frequency']].to_dict('records')
        
        # Long rare words (15+ characters, very low frequency)
        long_rare = self.words_df[(self.words_df['term_length'] >= 15) & (freq_data <= freq_data.quantile(0.05))]
        long_rare_sorted = long_rare.sort_values(['term_length', 'frequency'], ascending=[False, True])
        outliers['long_rare_words'] = long_rare_sorted.head(30)[['term', 'definition', 'frequency', 'term_length']].to_dict('records')
        
        # Short rare words (3-5 characters, very low frequency)
        short_rare = self.words_df[(self.words_df['term_length'].between(3, 5)) & (freq_data <= freq_data.quantile(0.01))]
        short_rare_sorted = short_rare.sort_values('frequency')
        outliers['short_rare_words'] = short_rare_sorted.head(30)[['term', 'definition', 'frequency', 'term_length']].to_dict('records')
        
        return outliers
    
    def analyze_part_of_speech_frequency(self):
        """Analyze frequency patterns by part of speech"""
        logger.info("Analyzing frequency by part of speech...")
        
        pos_stats = {}
        
        if 'part_of_speech' in self.words_df.columns:
            pos_groups = self.words_df.groupby('part_of_speech')['frequency']
            
            for pos, freq_series in pos_groups:
                if pd.isna(pos):
                    pos = 'Unknown'
                    
                pos_stats[pos] = {
                    'count': len(freq_series),
                    'mean_frequency': float(freq_series.mean()),
                    'median_frequency': float(freq_series.median()),
                    'rare_count': len(freq_series[freq_series <= freq_series.quantile(0.10)]),
                    'common_count': len(freq_series[freq_series >= freq_series.quantile(0.90)])
                }
        
        return pos_stats
    
    def create_visualizations(self):
        """Create frequency distribution visualizations"""
        logger.info("Creating visualizations...")
        
        # Set style
        plt.style.use('default')
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        
        # 1. Frequency distribution histogram
        freq_data = self.words_df['frequency']
        non_zero_freq = freq_data[freq_data > 0]
        
        axes[0,0].hist(np.log10(non_zero_freq + 1e-10), bins=50, alpha=0.7, edgecolor='black')
        axes[0,0].set_xlabel('Log10(Frequency)')
        axes[0,0].set_ylabel('Number of Words')
        axes[0,0].set_title('Word Frequency Distribution (Log Scale)')
        axes[0,0].grid(True, alpha=0.3)
        
        # 2. Rarity classification pie chart
        rarity_counts = self.words_df['rarity_class'].value_counts()
        axes[0,1].pie(rarity_counts.values, labels=rarity_counts.index, autopct='%1.1f%%')
        axes[0,1].set_title('Word Rarity Distribution')
        
        # 3. Frequency vs Length scatter plot
        sample_data = self.words_df.sample(min(2000, len(self.words_df)))  # Sample for clarity
        scatter = axes[1,0].scatter(sample_data['term_length'], 
                                  np.log10(sample_data['frequency'] + 1e-10),
                                  alpha=0.6, s=20)
        axes[1,0].set_xlabel('Word Length (characters)')
        axes[1,0].set_ylabel('Log10(Frequency)')
        axes[1,0].set_title('Frequency vs Word Length')
        axes[1,0].grid(True, alpha=0.3)
        
        # 4. Domain frequency boxplot (top domains only)
        if 'primary_domain' in self.words_df.columns:
            top_domains = self.words_df['primary_domain'].value_counts().head(8).index
            domain_data = []
            domain_labels = []
            
            for domain in top_domains:
                if pd.notna(domain):
                    domain_freq = self.words_df[self.words_df['primary_domain'] == domain]['frequency']
                    domain_freq_log = np.log10(domain_freq[domain_freq > 0] + 1e-10)
                    if len(domain_freq_log) > 0:
                        domain_data.append(domain_freq_log)
                        # Shorten domain names for display
                        short_name = domain.split('.')[-1] if '.' in domain else domain
                        domain_labels.append(short_name)
            
            if domain_data:
                axes[1,1].boxplot(domain_data, labels=domain_labels)
                axes[1,1].set_xlabel('Domain')
                axes[1,1].set_ylabel('Log10(Frequency)')
                axes[1,1].set_title('Frequency Distribution by Domain')
                axes[1,1].tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('frequency_analysis.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info("Visualizations saved as 'frequency_analysis.png'")
    
    def generate_report(self):
        """Generate comprehensive frequency analysis report"""
        logger.info("Generating comprehensive frequency report...")
        
        # Collect all analyses
        basic_stats = self.basic_frequency_statistics()
        rarity_dist, thresholds = self.rarity_classification()
        domain_stats = self.analyze_by_domain()
        length_stats = self.analyze_by_length()
        pos_stats = self.analyze_part_of_speech_frequency()
        outliers = self.find_interesting_outliers()
        
        # Print comprehensive report
        print("\n" + "="*80)
        print("COMPREHENSIVE VOCABULARY FREQUENCY ANALYSIS")
        print("="*80)
        
        # Basic statistics
        print(f"\nBASIC STATISTICS:")
        print("-" * 40)
        print(f"Total vocabulary terms: {basic_stats['total_words']:,}")
        print(f"Terms with frequency data: {basic_stats['words_with_frequency']:,}")
        print(f"Terms without frequency: {basic_stats['zero_frequency_words']:,}")
        print(f"Mean frequency: {basic_stats['mean_frequency']:.6f}")
        print(f"Median frequency: {basic_stats['median_frequency']:.6f}")
        print(f"Frequency range: {basic_stats['min_frequency']:.6f} - {basic_stats['max_frequency']:.3f}")
        
        # Rarity distribution
        print(f"\nRARITY DISTRIBUTION:")
        print("-" * 40)
        total_words = sum(rarity_dist.values())
        for rarity, count in sorted(rarity_dist.items(), key=lambda x: ['Ultra-Rare', 'Very Rare', 'Rare', 'Uncommon', 'Moderate', 'Common', 'Very Common', 'No Data'].index(x[0])):
            pct = (count / total_words) * 100
            print(f"{rarity:12s}: {count:5,} ({pct:5.1f}%)")
        
        # Rarity thresholds
        print(f"\nRARITY THRESHOLDS:")
        print("-" * 40)
        print(f"Ultra-rare (<={thresholds['ultra_rare_threshold']:.6f}): Bottom 1%")
        print(f"Very rare (<={thresholds['very_rare_threshold']:.6f}): Bottom 5%")
        print(f"Rare (<={thresholds['rare_threshold']:.6f}): Bottom 10%")
        print(f"Uncommon (<={thresholds['uncommon_threshold']:.6f}): Bottom 25%")
        
        # Domain analysis
        print(f"\nFREQUENCY BY DOMAIN:")
        print("-" * 60)
        if domain_stats:
            print(f"{'Domain':<25} {'Count':<8} {'Mean Freq':<12} {'Median Freq':<12}")
            print("-" * 60)
            for domain, stats in sorted(domain_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:10]:
                if stats['count'] > 50:  # Only show domains with substantial representation
                    domain_name = domain.replace('Scientific.Biological.', '') if 'Scientific.Biological.' in domain else domain
                    print(f"{domain_name[:24]:<25} {stats['count']:<8,} {stats['mean_frequency']:<12.6f} {stats['median_frequency']:<12.6f}")
        
        # Ultra-rare gems
        print(f"\nULTRA-RARE VOCABULARY GEMS (Top 20):")
        print("-" * 80)
        print(f"{'Word':<18} {'Frequency':<12} {'Domain':<20} {'Definition'}")
        print("-" * 80)
        for word in outliers['ultra_rare_gems'][:20]:
            domain = (word.get('primary_domain') or 'Unknown')[:19]
            definition = word['definition'][:50] + "..." if len(word['definition']) > 50 else word['definition']
            print(f"{word['term']:<18} {word['frequency']:<12.8f} {domain:<20} {definition}")
        
        # Long rare words
        print(f"\nLONG RARE WORDS (15+ characters):")
        print("-" * 70)
        print(f"{'Word':<22} {'Length':<8} {'Frequency':<12} {'Definition'}")
        print("-" * 70)
        for word in outliers['long_rare_words'][:15]:
            definition = word['definition'][:40] + "..." if len(word['definition']) > 40 else word['definition']
            print(f"{word['term']:<22} {word['term_length']:<8} {word['frequency']:<12.8f} {definition}")
        
        # Short rare words
        print(f"\nSHORT RARE WORDS (3-5 characters):")
        print("-" * 70)
        print(f"{'Word':<8} {'Length':<8} {'Frequency':<12} {'Definition'}")
        print("-" * 70)
        for word in outliers['short_rare_words'][:15]:
            definition = word['definition'][:50] + "..." if len(word['definition']) > 50 else word['definition']
            print(f"{word['term']:<8} {word['term_length']:<8} {word['frequency']:<12.8f} {definition}")
        
        # Part of speech analysis
        print(f"\nFREQUENCY BY PART OF SPEECH:")
        print("-" * 50)
        if pos_stats:
            print(f"{'POS':<12} {'Count':<8} {'Mean Freq':<12} {'% Rare':<8}")
            print("-" * 50)
            for pos, stats in sorted(pos_stats.items(), key=lambda x: x[1]['count'], reverse=True):
                if stats['count'] > 100:  # Only substantial categories
                    rare_pct = (stats['rare_count'] / stats['count']) * 100
                    print(f"{pos[:11]:<12} {stats['count']:<8,} {stats['mean_frequency']:<12.6f} {rare_pct:<8.1f}%")
        
        return {
            'basic_stats': basic_stats,
            'rarity_distribution': rarity_dist,
            'thresholds': thresholds,
            'domain_stats': domain_stats,
            'outliers': outliers
        }

def main():
    """Main analysis function"""
    print("Vocabulary Frequency Analysis")
    print("=" * 50)
    
    analyzer = FrequencyAnalyzer(get_db_config())
    
    # Load data
    analyzer.load_vocabulary_data()
    
    # Generate comprehensive analysis
    results = analyzer.generate_report()
    
    # Create visualizations
    analyzer.create_visualizations()
    
    print(f"\nAnalysis complete!")
    print("Check 'frequency_analysis.png' for visualizations")

if __name__ == "__main__":
    main()