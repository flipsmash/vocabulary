#!/usr/bin/env python3
"""
Update Missing Definitions Using Comprehensive Definition Lookup
Updates all terms in the defined table that have NULL or blank definitions
"""

import sys
import asyncio
import pymysql
from typing import List, Tuple, Optional
from core.config import VocabularyConfig
from core.comprehensive_definition_lookup import ComprehensiveDefinitionLookup
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_terms_with_missing_definitions() -> List[Tuple[int, str, Optional[str]]]:
    """Get all terms that have NULL or blank definitions"""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, term, part_of_speech
            FROM defined
            WHERE definition IS NULL OR definition = '' OR definition = ' '
            ORDER BY id
        """)

        results = cursor.fetchall()
        return [(row[0], row[1].strip(), row[2]) for row in results if row[1] and row[1].strip()]

    finally:
        cursor.close()
        conn.close()

def update_term_definition(term_id: int, definition: str, part_of_speech: str,
                          source: str, reliability: float) -> bool:
    """Update a single term's definition in the database"""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        # Update the definition and part of speech if needed
        if part_of_speech and part_of_speech != 'unknown':
            cursor.execute("""
                UPDATE defined
                SET definition = %s, part_of_speech = %s,
                    definition_source = %s, definition_reliability = %s,
                    definition_updated = NOW()
                WHERE id = %s
            """, (definition, part_of_speech, source, reliability, term_id))
        else:
            cursor.execute("""
                UPDATE defined
                SET definition = %s,
                    definition_source = %s, definition_reliability = %s,
                    definition_updated = NOW()
                WHERE id = %s
            """, (definition, source, reliability, term_id))

        conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        logger.error(f"Error updating term {term_id}: {e}")
        conn.rollback()
        return False

    finally:
        cursor.close()
        conn.close()

def add_definition_columns_if_needed():
    """Add definition tracking columns if they don't exist"""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        # Check if columns exist
        cursor.execute("SHOW COLUMNS FROM defined LIKE 'definition_source'")
        source_exists = cursor.fetchone() is not None

        cursor.execute("SHOW COLUMNS FROM defined LIKE 'definition_reliability'")
        reliability_exists = cursor.fetchone() is not None

        cursor.execute("SHOW COLUMNS FROM defined LIKE 'definition_updated'")
        updated_exists = cursor.fetchone() is not None

        # Add missing columns
        if not source_exists:
            print("Adding definition_source column...")
            cursor.execute("ALTER TABLE defined ADD COLUMN definition_source VARCHAR(50) DEFAULT NULL")

        if not reliability_exists:
            print("Adding definition_reliability column...")
            cursor.execute("ALTER TABLE defined ADD COLUMN definition_reliability DECIMAL(3,2) DEFAULT NULL")

        if not updated_exists:
            print("Adding definition_updated column...")
            cursor.execute("ALTER TABLE defined ADD COLUMN definition_updated TIMESTAMP DEFAULT NULL")

        conn.commit()
        return True

    except Exception as e:
        print(f"Error adding columns: {e}")
        return False

    finally:
        cursor.close()
        conn.close()

async def update_missing_definitions():
    """Main function to update all missing definitions"""
    print("=" * 60)
    print("Missing Definition Update System")
    print("=" * 60)

    # Add tracking columns if needed
    if not add_definition_columns_if_needed():
        print("Failed to add tracking columns")
        return False

    # Get terms with missing definitions
    missing_terms = get_terms_with_missing_definitions()
    print(f"Found {len(missing_terms):,} terms with missing definitions")

    if not missing_terms:
        print("No terms need definition updates!")
        return True

    # Process terms
    successful_updates = 0
    failed_updates = 0
    no_definition_found = 0

    async with ComprehensiveDefinitionLookup() as lookup_system:
        for i, (term_id, term, existing_pos) in enumerate(missing_terms, 1):
            print(f"\n[{i:,}/{len(missing_terms):,}] Processing: '{term}' (ID: {term_id})")

            try:
                # Look up definitions
                result = await lookup_system.lookup_term(term)

                if not result.definitions_by_pos:
                    print(f"  [NO DEF] No definitions found")
                    no_definition_found += 1
                    continue

                # Try to match existing part of speech first
                best_definition = None
                matched_pos = False

                if existing_pos and existing_pos.lower() in result.definitions_by_pos:
                    # Use definition matching existing POS
                    pos_definitions = result.definitions_by_pos[existing_pos.lower()]
                    if pos_definitions:
                        best_definition = max(pos_definitions, key=lambda d: d.reliability_score)
                        matched_pos = True
                        print(f"  [MATCH] Matched existing POS: {existing_pos}")

                # If no POS match, get best overall definition
                if not best_definition:
                    best_definition = result.get_best_definition()

                if best_definition:
                    # Update database
                    success = update_term_definition(
                        term_id=term_id,
                        definition=best_definition.text,
                        part_of_speech=best_definition.part_of_speech if not matched_pos else existing_pos,
                        source=best_definition.source,
                        reliability=best_definition.reliability_score
                    )

                    if success:
                        successful_updates += 1
                        pos_indicator = "MATCH" if matched_pos else "NEW"
                        print(f"  [SUCCESS] Updated - {pos_indicator} POS: {best_definition.part_of_speech}")
                        print(f"     Source: {best_definition.source} (reliability: {best_definition.reliability_score:.2f})")
                        print(f"     Definition: {best_definition.text[:80]}{'...' if len(best_definition.text) > 80 else ''}")

                        # Show all available definitions for context
                        total_defs = sum(len(defs) for defs in result.definitions_by_pos.values())
                        if total_defs > 1:
                            print(f"     Found {total_defs} total definitions across {len(result.definitions_by_pos)} POS categories")
                    else:
                        print(f"  [FAILED] Database update failed")
                        failed_updates += 1
                else:
                    print(f"  [NO DEF] No usable definitions found")
                    no_definition_found += 1

            except Exception as e:
                print(f"  [ERROR] Error processing '{term}': {e}")
                failed_updates += 1

            # Progress update every 10 terms
            if i % 10 == 0:
                print(f"\n--- Progress Update ---")
                print(f"Processed: {i:,}/{len(missing_terms):,}")
                print(f"Successful: {successful_updates:,}")
                print(f"Failed: {failed_updates:,}")
                print(f"No definitions: {no_definition_found:,}")

    # Final results
    print(f"\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Terms processed: {len(missing_terms):,}")
    print(f"Successful updates: {successful_updates:,}")
    print(f"Failed updates: {failed_updates:,}")
    print(f"No definitions found: {no_definition_found:,}")
    print(f"Success rate: {successful_updates/len(missing_terms)*100:.1f}%")

    return successful_updates > 0

async def check_missing_definitions_status():
    """Check current status of missing definitions"""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        # Total terms
        cursor.execute("SELECT COUNT(*) FROM defined")
        total_terms = cursor.fetchone()[0]

        # Terms with definitions
        cursor.execute("SELECT COUNT(*) FROM defined WHERE definition IS NOT NULL AND definition != '' AND definition != ' '")
        with_definitions = cursor.fetchone()[0]

        # Terms without definitions
        cursor.execute("SELECT COUNT(*) FROM defined WHERE definition IS NULL OR definition = '' OR definition = ' '")
        without_definitions = cursor.fetchone()[0]

        print(f"Definition Status:")
        print(f"  Total terms: {total_terms:,}")
        print(f"  With definitions: {with_definitions:,}")
        print(f"  Missing definitions: {without_definitions:,}")
        print(f"  Coverage: {with_definitions/total_terms*100:.1f}%")

        # Check if tracking columns exist
        cursor.execute("SHOW COLUMNS FROM defined LIKE 'definition_source'")
        has_source = cursor.fetchone() is not None

        if has_source:
            cursor.execute("SELECT COUNT(*) FROM defined WHERE definition_source IS NOT NULL")
            with_source = cursor.fetchone()[0]
            print(f"  With source tracking: {with_source:,}")

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        asyncio.run(check_missing_definitions_status())
    else:
        try:
            success = asyncio.run(update_missing_definitions())

            if success:
                print("\nOperation completed successfully!")
            else:
                print("\nOperation failed!")
                sys.exit(1)

        except KeyboardInterrupt:
            print("\nOperation cancelled by user")
            sys.exit(1)
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)