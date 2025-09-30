#!/usr/bin/env python3
"""
Domain-Specific Frequency Analysis
Analyze frequency patterns across different domains
"""

import mysql.connector
import json
import logging
from collections import defaultdict, Counter
from config import get_db_config
import statistics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_domain_frequencies():
    """Analyze frequency patterns by domain"""
    logger.info("Starting domain-specific frequency analysis...")
    
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    
    # Get all words with their domains and frequencies
    cursor.execute("""
        SELECT 
            d.term,
            d.part_of_speech,
            wd.primary_domain,
            wd.all_domains,
            wfi.independent_frequency,
            wfi.frequency_rank,
            wfi.rarity_percentile,
            wfi.source_frequencies
        FROM defined d
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        WHERE wfi.independent_frequency IS NOT NULL
        ORDER BY wfi.frequency_rank
    """)
    
    results = cursor.fetchall()
    logger.info(f"Retrieved {len(results)} words with frequency data")
    
    # Organize data by domain
    domain_data = defaultdict(list)
    pos_data = defaultdict(list)
    source_analysis = defaultdict(lambda: defaultdict(list))
    
    for term, pos, primary_domain, all_domains, ind_freq, freq_rank, rarity_pct, source_freq_json in results:
        if primary_domain:
            domain_data[primary_domain].append({
                'term': term,
                'pos': pos,
                'frequency': ind_freq,
                'rank': freq_rank,
                'rarity': rarity_pct,
                'sources': json.loads(source_freq_json) if source_freq_json else {}
            })
            
            # Analyze source contributions by domain
            if source_freq_json:
                sources = json.loads(source_freq_json)
                for source, value in sources.items():
                    if value is not None and value > 0:
                        source_analysis[primary_domain][source].append(value)
        
        if pos:
            pos_data[pos].append({
                'term': term,
                'domain': primary_domain,
                'frequency': ind_freq,
                'rank': freq_rank,
                'rarity': rarity_pct
            })
    
    # Generate comprehensive analysis report
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("DOMAIN-SPECIFIC FREQUENCY ANALYSIS REPORT")
    report_lines.append("=" * 80)
    report_lines.append(f"Analysis Date: {logger.handlers[0].formatter.formatTime if logger.handlers else 'N/A'}")
    report_lines.append(f"Total Words Analyzed: {len(results):,}")
    report_lines.append(f"Total Domains: {len(domain_data)}")
    report_lines.append(f"Total Parts of Speech: {len(pos_data)}")
    report_lines.append("")
    
    # Domain Statistics
    report_lines.append("DOMAIN STATISTICS")
    report_lines.append("-" * 40)
    
    domain_stats = []
    for domain, words in domain_data.items():
        frequencies = [w['frequency'] for w in words]
        ranks = [w['rank'] for w in words]
        rarities = [w['rarity'] for w in words if w['rarity'] is not None]
        
        if frequencies:
            stats = {
                'domain': domain,
                'word_count': len(words),
                'avg_frequency': statistics.mean(frequencies),
                'median_frequency': statistics.median(frequencies),
                'avg_rank': statistics.mean(ranks),
                'median_rank': statistics.median(ranks),
                'avg_rarity': statistics.mean(rarities) if rarities else None,
                'most_common_pos': Counter([w['pos'] for w in words if w['pos']]).most_common(1)[0] if any(w['pos'] for w in words) else None
            }
            domain_stats.append(stats)
    
    # Sort domains by average frequency (higher = more frequent)
    domain_stats.sort(key=lambda x: x['avg_frequency'], reverse=True)
    
    report_lines.append(f"{'Domain':<25} {'Words':<8} {'Avg Freq':<12} {'Med Freq':<12} {'Avg Rank':<10} {'Avg Rarity':<10}")
    report_lines.append("-" * 90)
    
    for stats in domain_stats:
        avg_rarity_str = f"{stats['avg_rarity']:.1f}%" if stats['avg_rarity'] is not None else "N/A"
        report_lines.append(
            f"{stats['domain'][:24]:<25} "
            f"{stats['word_count']:<8,} "
            f"{stats['avg_frequency']:<12.2e} "
            f"{stats['median_frequency']:<12.2e} "
            f"{stats['avg_rank']:<10,.0f} "
            f"{avg_rarity_str:<10}"
        )
    
    report_lines.append("")
    
    # Top 10 Most Frequent Domains
    report_lines.append("TOP 10 DOMAINS BY FREQUENCY")
    report_lines.append("-" * 40)
    for i, stats in enumerate(domain_stats[:10], 1):
        most_common_pos = stats['most_common_pos'][0] if stats['most_common_pos'] else "N/A"
        report_lines.append(f"{i:2d}. {stats['domain']}")
        report_lines.append(f"    Words: {stats['word_count']:,} | Avg Frequency: {stats['avg_frequency']:.2e}")
        report_lines.append(f"    Most Common POS: {most_common_pos}")
        report_lines.append("")
    
    # Bottom 10 Least Frequent Domains  
    report_lines.append("BOTTOM 10 DOMAINS BY FREQUENCY")
    report_lines.append("-" * 40)
    for i, stats in enumerate(domain_stats[-10:], 1):
        most_common_pos = stats['most_common_pos'][0] if stats['most_common_pos'] else "N/A"
        report_lines.append(f"{i:2d}. {stats['domain']}")
        report_lines.append(f"    Words: {stats['word_count']:,} | Avg Frequency: {stats['avg_frequency']:.2e}")
        report_lines.append(f"    Most Common POS: {most_common_pos}")
        report_lines.append("")
    
    # Part of Speech Analysis
    report_lines.append("PART OF SPEECH FREQUENCY ANALYSIS")
    report_lines.append("-" * 40)
    
    pos_stats = []
    for pos, words in pos_data.items():
        frequencies = [w['frequency'] for w in words]
        ranks = [w['rank'] for w in words]
        
        if frequencies:
            pos_stats.append({
                'pos': pos,
                'word_count': len(words),
                'avg_frequency': statistics.mean(frequencies),
                'median_frequency': statistics.median(frequencies),
                'avg_rank': statistics.mean(ranks)
            })
    
    pos_stats.sort(key=lambda x: x['avg_frequency'], reverse=True)
    
    report_lines.append(f"{'Part of Speech':<15} {'Words':<8} {'Avg Frequency':<15} {'Med Frequency':<15} {'Avg Rank':<10}")
    report_lines.append("-" * 70)
    
    for stats in pos_stats:
        report_lines.append(
            f"{stats['pos']:<15} "
            f"{stats['word_count']:<8,} "
            f"{stats['avg_frequency']:<15.2e} "
            f"{stats['median_frequency']:<15.2e} "
            f"{stats['avg_rank']:<10,.0f}"
        )
    
    report_lines.append("")
    
    # Source Analysis by Domain
    report_lines.append("FREQUENCY SOURCE ANALYSIS BY DOMAIN")
    report_lines.append("-" * 40)
    
    for domain in sorted(source_analysis.keys())[:10]:  # Top 10 domains by name
        report_lines.append(f"\n{domain}:")
        sources_data = source_analysis[domain]
        
        for source, values in sources_data.items():
            if values and source != 'corpus':  # Skip corpus since it's now 0%
                avg_val = statistics.mean(values)
                report_lines.append(f"  {source:>12}: {avg_val:>10.2e} (from {len(values):,} words)")
    
    # Write report
    report_content = "\n".join(report_lines)
    
    with open('domain_frequency_analysis_report.txt', 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    logger.info("Domain frequency analysis complete!")
    logger.info("Report saved to: domain_frequency_analysis_report.txt")
    
    # Print summary to console
    print("\nDOMAIN FREQUENCY ANALYSIS SUMMARY")
    print("=" * 50)
    print(f"Total words analyzed: {len(results):,}")
    print(f"Total domains: {len(domain_data)}")
    print("\nTop 5 Most Frequent Domains:")
    for i, stats in enumerate(domain_stats[:5], 1):
        print(f"{i}. {stats['domain']} ({stats['word_count']:,} words)")
    
    print("\nTop 5 Parts of Speech by Frequency:")
    for i, stats in enumerate(pos_stats[:5], 1):
        print(f"{i}. {stats['pos']} ({stats['word_count']:,} words)")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    analyze_domain_frequencies()