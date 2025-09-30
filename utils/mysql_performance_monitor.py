#!/usr/bin/env python3
"""
MySQL Performance Monitor for High-Volume Insert Operations
Monitors key metrics during similarity insert operations
"""

import mysql.connector
import time
import json
from datetime import datetime
from typing import Dict, List

class MySQLPerformanceMonitor:
    """Monitor MySQL performance metrics during bulk inserts"""
    
    def __init__(self, db_config):
        self.db_config = db_config
        self.baseline_metrics = None
        self.monitoring = False
        
    def get_connection(self):
        """Get database connection"""
        return mysql.connector.connect(**self.db_config)
    
    def get_key_metrics(self) -> Dict:
        """Get key performance metrics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            metrics = {}
            
            # Buffer Pool Metrics
            cursor.execute("SHOW STATUS LIKE 'Innodb_buffer_pool%'")
            buffer_metrics = dict(cursor.fetchall())
            
            # Calculate buffer pool hit ratio
            reads = float(buffer_metrics.get('Innodb_buffer_pool_reads', 0))
            read_requests = float(buffer_metrics.get('Innodb_buffer_pool_read_requests', 1))
            hit_ratio = ((read_requests - reads) / read_requests * 100) if read_requests > 0 else 0
            
            metrics['buffer_pool_hit_ratio'] = hit_ratio
            metrics['buffer_pool_size'] = buffer_metrics.get('Innodb_buffer_pool_size', 0)
            
            # Helper function for safe status retrieval
            def get_status_value(status_name, default=0):
                try:
                    cursor.execute(f"SHOW STATUS LIKE '{status_name}'")
                    result = cursor.fetchone()
                    return int(result[1]) if result and len(result) > 1 else default
                except:
                    return default
            
            # Insert Performance
            metrics['total_inserts'] = get_status_value('Com_insert')
            
            # Lock Metrics
            metrics['lock_time_ms'] = get_status_value('Innodb_lock_time')
            metrics['lock_waits'] = get_status_value('Innodb_lock_waits')
            
            # Log Metrics
            metrics['log_writes'] = get_status_value('Innodb_log_writes')
            metrics['log_write_requests'] = get_status_value('Innodb_log_write_requests')
            
            # I/O Metrics
            metrics['data_writes'] = get_status_value('Innodb_data_writes')
            metrics['data_read_bytes'] = get_status_value('Innodb_data_read')
            metrics['data_written_bytes'] = get_status_value('Innodb_data_written')
            
            # Connection metrics
            metrics['active_connections'] = get_status_value('Threads_connected')
            metrics['running_threads'] = get_status_value('Threads_running')
            
            # Table specific metrics
            cursor.execute("""
                SELECT TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH 
                FROM information_schema.tables 
                WHERE TABLE_SCHEMA = 'vocab' 
                AND TABLE_NAME = 'pronunciation_similarity'
            """)
            result = cursor.fetchone()
            if result:
                metrics['similarity_table_rows'] = result[0] or 0
                metrics['similarity_data_mb'] = (result[1] or 0) / (1024*1024)
                metrics['similarity_index_mb'] = (result[2] or 0) / (1024*1024)
            
            metrics['timestamp'] = datetime.now().isoformat()
            
        return metrics
    
    def get_configuration(self) -> Dict:
        """Get key MySQL configuration variables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            config_vars = [
                'innodb_buffer_pool_size',
                'innodb_log_file_size', 
                'innodb_log_buffer_size',
                'innodb_flush_log_at_trx_commit',
                'innodb_flush_method',
                'innodb_write_io_threads',
                'innodb_read_io_threads',
                'max_connections',
                'sql_log_bin',
                'sync_binlog',
                'query_cache_type',
                'innodb_io_capacity',
                'bulk_insert_buffer_size'
            ]
            
            config = {}
            for var in config_vars:
                try:
                    cursor.execute(f"SHOW VARIABLES LIKE '{var}'")
                    result = cursor.fetchone()
                    if result and len(result) > 1:
                        config[var] = result[1]
                    else:
                        config[var] = "Not found"
                except Exception as e:
                    config[var] = f"Error: {e}"
                    
            return config
    
    def start_monitoring(self, interval_seconds: int = 10):
        """Start continuous monitoring"""
        print("🔍 Starting MySQL Performance Monitoring...")
        print(f"Monitoring interval: {interval_seconds} seconds")
        
        # Get baseline
        self.baseline_metrics = self.get_key_metrics()
        print(f"Baseline established at {self.baseline_metrics['timestamp']}")
        
        # Show configuration
        config = self.get_configuration()
        print("\n📊 Key Configuration:")
        print(f"Buffer Pool Size: {config.get('innodb_buffer_pool_size', 'Unknown')}")
        print(f"Log File Size: {config.get('innodb_log_file_size', 'Unknown')}")
        print(f"Flush Log at Commit: {config.get('innodb_flush_log_at_trx_commit', 'Unknown')}")
        print(f"Binary Logging: {config.get('sql_log_bin', 'Unknown')}")
        print(f"Max Connections: {config.get('max_connections', 'Unknown')}")
        
        self.monitoring = True
        start_time = time.time()
        
        try:
            while self.monitoring:
                time.sleep(interval_seconds)
                
                current_metrics = self.get_key_metrics()
                elapsed = time.time() - start_time
                
                # Calculate deltas from baseline
                insert_delta = current_metrics['total_inserts'] - self.baseline_metrics['total_inserts']
                insert_rate = insert_delta / elapsed if elapsed > 0 else 0
                
                lock_time_delta = current_metrics['lock_time_ms'] - self.baseline_metrics['lock_time_ms']
                lock_wait_delta = current_metrics['lock_waits'] - self.baseline_metrics['lock_waits']
                
                log_write_delta = current_metrics['log_writes'] - self.baseline_metrics['log_writes']
                
                data_written_delta = current_metrics['data_written_bytes'] - self.baseline_metrics['data_written_bytes']
                data_written_mb = data_written_delta / (1024*1024)
                
                # Print status
                print(f"\n⚡ Performance Status ({elapsed/60:.1f} min elapsed):")
                print(f"   Inserts: {insert_delta:,} total ({insert_rate:.0f}/sec)")
                print(f"   Buffer Hit Ratio: {current_metrics['buffer_pool_hit_ratio']:.2f}%")
                print(f"   Lock Time: +{lock_time_delta}ms, Lock Waits: +{lock_wait_delta}")
                print(f"   Log Writes: +{log_write_delta}")
                print(f"   Data Written: {data_written_mb:.1f} MB")
                print(f"   Active Connections: {current_metrics['active_connections']}")
                print(f"   Table Rows: {current_metrics['similarity_table_rows']:,}")
                print(f"   Table Size: {current_metrics['similarity_data_mb']:.1f} MB")
                
                # Performance warnings
                if current_metrics['buffer_pool_hit_ratio'] < 95:
                    print("   ⚠️  LOW BUFFER POOL HIT RATIO - Consider increasing innodb_buffer_pool_size")
                
                if lock_wait_delta > 1000:
                    print("   ⚠️  HIGH LOCK WAITS - Consider optimizing concurrency")
                
                if insert_rate < 1000:
                    print("   ⚠️  LOW INSERT RATE - Check for bottlenecks")
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
            self.monitoring = False
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring = False
    
    def get_performance_report(self) -> Dict:
        """Generate a performance report"""
        current_metrics = self.get_key_metrics()
        config = self.get_configuration()
        
        if self.baseline_metrics:
            insert_delta = current_metrics['total_inserts'] - self.baseline_metrics['total_inserts']
            
            # Calculate time difference
            baseline_time = datetime.fromisoformat(self.baseline_metrics['timestamp'])
            current_time = datetime.fromisoformat(current_metrics['timestamp'])
            elapsed_seconds = (current_time - baseline_time).total_seconds()
            
            insert_rate = insert_delta / elapsed_seconds if elapsed_seconds > 0 else 0
        else:
            insert_rate = 0
            elapsed_seconds = 0
        
        report = {
            'monitoring_duration_minutes': elapsed_seconds / 60,
            'total_inserts_during_monitoring': insert_delta if self.baseline_metrics else 0,
            'average_insert_rate_per_second': insert_rate,
            'buffer_pool_hit_ratio': current_metrics['buffer_pool_hit_ratio'],
            'current_table_rows': current_metrics['similarity_table_rows'],
            'current_table_size_mb': current_metrics['similarity_data_mb'],
            'active_connections': current_metrics['active_connections'],
            'key_configuration': config,
            'recommendations': []
        }
        
        # Generate recommendations
        if current_metrics['buffer_pool_hit_ratio'] < 95:
            report['recommendations'].append("Increase innodb_buffer_pool_size for better cache hit ratio")
        
        if insert_rate < 10000:
            report['recommendations'].append("Consider MySQL optimizations from MYSQL_OPTIMIZATION_GUIDE.md")
        
        if config.get('sql_log_bin', '').upper() == 'ON':
            report['recommendations'].append("Consider disabling binary logging (sql_log_bin=0) for faster inserts")
        
        return report


def main():
    """Main function for standalone monitoring"""
    from config import get_db_config
    DB_CONFIG = get_db_config()
    
    monitor = MySQLPerformanceMonitor(DB_CONFIG)
    
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'report':
        # Generate one-time report
        report = monitor.get_performance_report()
        print(json.dumps(report, indent=2))
    else:
        # Start continuous monitoring
        try:
            monitor.start_monitoring(interval_seconds=10)
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")


if __name__ == "__main__":
    main()