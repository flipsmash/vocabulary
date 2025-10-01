    async def run_autonomous_session(self) -> Dict:
        """Run a complete autonomous spidering session"""
        logger.info(f"Starting autonomous spider session {self.session_id}")
        logger.info(f"Config: {self.config.max_urls_per_source} URLs/source, "
                   f"{self.config.max_session_duration_minutes}min max, "
                   f"zipf≤{self.config.zipf_threshold}")
        
        # Setup database
        await self.setup_database_tables()
        
        all_candidates = []
        session_start = datetime.now()
        
        # Initialize definition lookup in async context
        from core.comprehensive_definition_lookup import ComprehensiveDefinitionLookup
        async with ComprehensiveDefinitionLookup() as definition_lookup:
            self.definition_lookup = definition_lookup
            
            try:
                # Continue until limits reached
                while (len(all_candidates) < self.config.max_total_candidates and
                       (datetime.now() - session_start).total_seconds() < self.config.max_session_duration_minutes * 60):
                    
                    # Adaptively select source
                    source_type = self.select_next_source()
                    
                    # Calculate dynamic URL limit based on performance
                    performance = self.performance_metrics[source_type]
                    if performance.success_rate > 0.7:
                        urls_to_process = min(self.config.max_urls_per_source, 20)
                    elif performance.success_rate > 0.3:
                        urls_to_process = min(self.config.max_urls_per_source, 10)
                    else:
                        urls_to_process = min(self.config.max_urls_per_source, 5)
                    
                    # Process URLs from selected source
                    logger.info(f"Processing {urls_to_process} URLs from {source_type.value}")
                    source_candidates = await self.process_urls_from_source(source_type, urls_to_process)
                    
                    if source_candidates:
                        all_candidates.extend(source_candidates)
                        self.total_candidates_found += len(source_candidates)
                        
                        # Store candidates periodically
                        await self.store_candidates(source_candidates)
                    
                    logger.info(f"Session progress: {len(all_candidates)} total candidates, "
                               f"{self.total_urls_visited} URLs visited")
            
            except KeyboardInterrupt:
                logger.info("Session interrupted by user")
            except Exception as e:
                logger.error(f"Session error: {e}")
        
        # Final session summary
        duration = datetime.now() - session_start