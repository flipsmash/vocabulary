-- Database Cleanup Script
-- Generated automatically - contains only SAFE to remove tables
-- Generated on: 2025-09-07 11:52:22.261904

-- Disable foreign key checks for cleanup
SET FOREIGN_KEY_CHECKS = 0;

-- candidate_review_queue: Empty table, no relationships (0.00 MB, 0 rows)
DROP TABLE IF EXISTS candidate_review_queue;

-- Re-enable foreign key checks
SET FOREIGN_KEY_CHECKS = 1;
