INSERT INTO platform.plans(code,name) VALUES ('TRIAL','Plan de prueba');
INSERT INTO platform.plan_versions(plan_id,version,monthly_price) SELECT id,1,0 FROM platform.plans WHERE code='TRIAL';
INSERT INTO platform.features(code,name) VALUES
 ('CRM','CRM'),('ICMP','ICMP'),('SNMP','SNMP'),('INVENTORY','Inventario y activos'),('BILLING','Cobros'),('SUPPORT','Tickets y ordenes'),('REPORTS','Reportes'),('FLOW','Traffic Flow / IPFIX');
INSERT INTO platform.plan_features(plan_version_id,feature_id)
SELECT v.id,f.id FROM platform.plan_versions v JOIN platform.plans p ON p.id=v.plan_id CROSS JOIN platform.features f WHERE p.code='TRIAL' AND v.version=1 AND f.code <> 'FLOW';
-- El catalogo de funciones no significa que esten implementadas. NULL en limites/duracion = sin limite.
INSERT INTO platform.settings(default_plan_version_id)
SELECT v.id FROM platform.plan_versions v JOIN platform.plans p ON p.id=v.plan_id WHERE p.code='TRIAL' AND v.version=1;
