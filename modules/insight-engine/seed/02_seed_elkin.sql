-- Catalyst Civic — Elkin, NC test seed (SYNTHETIC fixture)
--
-- Models the Town of Elkin (Surry County, NC) Board of Commissioners. The
-- geography and issue areas are real (Big Elkin Creek, the Municipal Park,
-- Main Street / downtown, the water plant, Yadkin Valley tourism); the
-- council members, the developer, dollar figures, and quotes are FICTIONAL.
-- This exists to exercise the insight engine end to end, not to make claims
-- about real Elkin officials. Sized to clear the lenses' default thresholds.
--
-- Load after 01_source_schema_mirror.sql.

-- ============================ AGENDA MEETINGS =============================
INSERT INTO m1_agenda.meetings (meeting_id, source_id, jurisdiction, meeting_type, meeting_date, location) VALUES
 ('ELK_2023_05_08','RUN_ELK_2305','Town of Elkin','Board of Commissioners','2023-05-08','Elkin Town Hall'),
 ('ELK_2023_09_11','RUN_ELK_2309','Town of Elkin','Board of Commissioners','2023-09-11','Elkin Town Hall'),
 ('ELK_2024_01_08','RUN_ELK_2401','Town of Elkin','Board of Commissioners','2024-01-08','Elkin Town Hall'),
 ('ELK_2024_05_13','RUN_ELK_2405','Town of Elkin','Board of Commissioners','2024-05-13','Elkin Town Hall'),
 ('ELK_2024_09_09','RUN_ELK_2409','Town of Elkin','Board of Commissioners','2024-09-09','Elkin Town Hall'),
 ('ELK_2025_02_10','RUN_ELK_2502','Town of Elkin','Board of Commissioners','2025-02-10','Elkin Town Hall'),
 ('ELK_2025_06_09','RUN_ELK_2506','Town of Elkin','Board of Commissioners','2025-06-09','Elkin Town Hall'),
 ('ELK_2026_03_09','RUN_ELK_2603','Town of Elkin','Board of Commissioners','2026-03-09','Elkin Town Hall')
ON CONFLICT DO NOTHING;

-- ============================== AGENDA ITEMS =============================
-- Water & sewer item in every meeting (clears the topics lens: 8 meetings).
INSERT INTO m1_agenda.items (item_id, meeting_id, ordinal, label, title, item_type, content) VALUES
 ('ITM_2305_W','ELK_2023_05_08',3,'5a','Water and sewer rate study update','ITEM','Staff presented the annual water and sewer rate study for the utility fund.'),
 ('ITM_2309_W','ELK_2023_09_11',2,'4b','Sewer line rehabilitation on Gwyn Avenue','ITEM','Discussion of sewer line rehabilitation and inflow reduction on Gwyn Avenue.'),
 ('ITM_2401_W','ELK_2024_01_08',4,'6a','Water plant filtration upgrade scoping','ITEM','Engineering scope for the water treatment plant filtration upgrade was reviewed.'),
 ('ITM_2405_W','ELK_2024_05_13',2,'4a','Water and sewer capital plan','ITEM','Adoption of the five year water and sewer capital improvement plan.'),
 ('ITM_2409_W','ELK_2024_09_09',5,'7c','Big Elkin Creek stormwater and sewer crossing','ITEM','Stormwater and sewer crossing improvements near Big Elkin Creek greenway.'),
 ('ITM_2502_W','ELK_2025_02_10',3,'5b','Water line replacement, North Bridge Street','ITEM','Water line replacement project on North Bridge Street utility corridor.'),
 ('ITM_2506_W','ELK_2025_06_09',2,'4c','Sewer capacity and annexation review','ITEM','Review of sewer capacity constraints relative to proposed annexation.'),
 ('ITM_2603_W','ELK_2026_03_09',4,'6b','Water and sewer fund budget amendment','ITEM','Budget amendment for the water and sewer enterprise fund.')
ON CONFLICT DO NOTHING;

-- Spending items with dollar figures (clears the spending lens).
INSERT INTO m1_agenda.items (item_id, meeting_id, ordinal, label, title, item_type, content) VALUES
 ('ITM_2401_PLANT','ELK_2024_01_08',5,'6b','Appropriation: water treatment plant filtration upgrade','ITEM','Appropriation of $2,400,000 for the water treatment plant filtration upgrade, partially grant funded.'),
 ('ITM_2405_FIRE','ELK_2024_05_13',6,'8a','Purchase of fire pumper apparatus','ITEM','Authorized purchase of a fire pumper apparatus in the amount of $585,000.'),
 ('ITM_2409_PAVE','ELK_2024_09_09',7,'9a','Main Street resurfacing contract','ITEM','Award of the Main Street downtown resurfacing contract for $312,500.'),
 ('ITM_2502_GREENWAY','ELK_2025_02_10',5,'7a','Big Elkin Creek greenway grant match','ITEM','Local match of $185,000 for the Big Elkin Creek greenway extension grant.'),
 ('ITM_2506_PARK','ELK_2025_06_09',5,'7b','Elkin Municipal Park restroom replacement','ITEM','Contract for Elkin Municipal Park restroom replacement at $96,000.')
ON CONFLICT DO NOTHING;

-- Development / rezoning items that name the recurring developer entity.
INSERT INTO m1_agenda.items (item_id, meeting_id, ordinal, label, title, item_type, content) VALUES
 ('ITM_2309_RZ','ELK_2023_09_11',5,'7a','Rezoning request, Crater Ridge Development','ITEM','Public hearing on a rezoning request submitted by Crater Ridge Development LLC for parcels off Klondike Road.'),
 ('ITM_2405_RZ','ELK_2024_05_13',7,'8c','Conditional use, Crater Ridge Development','ITEM','Conditional use permit for a residential project by Crater Ridge Development LLC near the Yadkin Valley gateway.'),
 ('ITM_2603_DT','ELK_2026_03_09',5,'7a','Downtown revitalization facade grants','ITEM','Approval of downtown Main Street facade improvement grants for the revitalization program.')
ON CONFLICT DO NOTHING;

-- ============================ AUTHORITY LAYER ============================
INSERT INTO cco.registry (registry_id, category, canonical_name) VALUES
 ('reg_crater','ORGANIZATION','Crater Ridge Development LLC'),
 ('reg_planning','BOARD','Elkin Planning Board'),
 ('reg_whitaker','PEOPLE','Commissioner Dana Whitaker'),
 ('reg_yvwt','ORGANIZATION','Yadkin Valley Wine Trail')
ON CONFLICT DO NOTHING;

INSERT INTO cco.identities (registry_id, alias_name, source_id) VALUES
 ('reg_crater','Crater Ridge Development LLC','RUN_ELK_2309'),
 ('reg_crater','Crater Ridge Dev','RUN_ELK_2405'),
 ('reg_crater','Crater Ridge','RUN_ELK_2506'),
 ('reg_whitaker','Commissioner Dana Whitaker','RUN_ELK_2409'),
 ('reg_whitaker','Dana Whitaker','RUN_ELK_2506')
ON CONFLICT DO NOTHING;

-- Crater Ridge: observed across 6 distinct source_ids (clears influence MIN_RECORDS=5).
INSERT INTO cco.observations (registry_id, fact_key, fact_value, source_id, evidence, effective_date) VALUES
 ('reg_crater','MENTIONED_IN_RECORD','{"context":"rezoning request off Klondike Road"}','RUN_ELK_2309','Rezoning request submitted by Crater Ridge Development LLC','2023-09-11'),
 ('reg_crater','MENTIONED_IN_RECORD','{"context":"conditional use permit, Yadkin Valley gateway"}','RUN_ELK_2405','Conditional use permit for Crater Ridge Development LLC','2024-05-13'),
 ('reg_crater','PROPERTY_STREET_ADDRESS','{"context":"parcels off Klondike Road"}','RUN_ELK_2409','Crater Ridge parcels referenced in stormwater discussion','2024-09-09'),
 ('reg_crater','MENTIONED_IN_RECORD','{"context":"sewer capacity vs proposed annexation"}','RUN_ELK_2506','Crater Ridge annexation and sewer capacity review','2025-06-09'),
 ('reg_crater','MENTIONED_IN_RECORD','{"context":"phased residential plat"}','RUN_ELK_2502','Crater Ridge phased plat referenced','2025-02-10'),
 ('reg_crater','MENTIONED_IN_RECORD','{"context":"downtown gateway frontage"}','RUN_ELK_2603','Crater Ridge frontage near downtown gateway','2026-03-09')
ON CONFLICT DO NOTHING;

-- Planning Board: observed across 5 distinct source_ids (clears threshold).
INSERT INTO cco.observations (registry_id, fact_key, fact_value, source_id, evidence, effective_date) VALUES
 ('reg_planning','MENTIONED_IN_RECORD','{"context":"recommendation on rezoning"}','RUN_ELK_2309','Planning Board recommendation noted','2023-09-11'),
 ('reg_planning','MENTIONED_IN_RECORD','{"context":"capital plan review"}','RUN_ELK_2405','Planning Board reviewed capital plan','2024-05-13'),
 ('reg_planning','MENTIONED_IN_RECORD','{"context":"greenway alignment"}','RUN_ELK_2502','Planning Board greenway alignment input','2025-02-10'),
 ('reg_planning','MENTIONED_IN_RECORD','{"context":"annexation study"}','RUN_ELK_2506','Planning Board annexation study','2025-06-09'),
 ('reg_planning','MENTIONED_IN_RECORD','{"context":"downtown overlay"}','RUN_ELK_2603','Planning Board downtown overlay discussion','2026-03-09')
ON CONFLICT DO NOTHING;

-- Below-threshold entities (exercise the influence filter; should NOT surface at defaults).
INSERT INTO cco.observations (registry_id, fact_key, fact_value, source_id, evidence, effective_date) VALUES
 ('reg_whitaker','MENTIONED_IN_RECORD','{"context":"moved to adopt capital plan"}','RUN_ELK_2409','Commissioner Whitaker moved adoption','2024-09-09'),
 ('reg_whitaker','MENTIONED_IN_RECORD','{"context":"annexation discussion"}','RUN_ELK_2506','Commissioner Whitaker comments','2025-06-09'),
 ('reg_yvwt','MENTIONED_IN_RECORD','{"context":"tourism partnership"}','RUN_ELK_2405','Yadkin Valley Wine Trail partnership','2024-05-13')
ON CONFLICT DO NOTHING;

-- ============================ TRANSCRIPT LANE ============================
INSERT INTO m1_transcript.meetings (meeting_id, source_id, jurisdiction, meeting_date, disposition_code, pass_95_gate, total_turns) VALUES
 ('ELK_2024_09_09','RUN_ELK_2409_TS','Town of Elkin','2024-09-09','OK95', true, 10)
ON CONFLICT DO NOTHING;

-- Motion/vote-dense session (clears votes lens: >= 8 procedural turns).
INSERT INTO m1_transcript.turns (meeting_id, turn_id, ordinal, phase, speaker_role, speaker_name, content) VALUES
 ('ELK_2024_09_09','t1',1,'OPENING','PRESIDER','Mayor','We will call the meeting to order.'),
 ('ELK_2024_09_09','t2',2,'MOTION','MEMBER','Commissioner Dana Whitaker','I move to adopt the Main Street resurfacing contract.'),
 ('ELK_2024_09_09','t3',3,'SECOND','MEMBER','Commissioner Reyes','Second.'),
 ('ELK_2024_09_09','t4',4,'DEBATE','MEMBER','Commissioner Hale','I would like clarification on the bid amount.'),
 ('ELK_2024_09_09','t5',5,'AMENDMENT','MEMBER','Commissioner Reyes','I move to amend to require local subcontractor outreach.'),
 ('ELK_2024_09_09','t6',6,'VOTE','PRESIDER','Mayor','All in favor of the amendment. The amendment carries.'),
 ('ELK_2024_09_09','t7',7,'VOTE','PRESIDER','Mayor','On the main motion as amended, all in favor. Motion carries four to one.'),
 ('ELK_2024_09_09','t8',8,'MOTION','MEMBER','Commissioner Hale','I move to adopt the stormwater crossing resolution near Big Elkin Creek.'),
 ('ELK_2024_09_09','t9',9,'SECOND','MEMBER','Commissioner Dana Whitaker','Second.'),
 ('ELK_2024_09_09','t10',10,'ADOPTION','PRESIDER','Mayor','The resolution is adopted.')
ON CONFLICT DO NOTHING;
