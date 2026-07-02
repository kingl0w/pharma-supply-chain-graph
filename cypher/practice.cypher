// practice queries for the supply graph in neo4j.
// load first with: make neo4j   (needs NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD)
// model: (Company)-[:MAKES]->(Product)-[:CONTAINS]->(Part)
// every relationship carries: source, confidence, as_of, source_record.

// 1. verify counts.
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC;
MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS n ORDER BY n DESC;

// 2. top makers by distinct product count (matches `make query` / `make rdf`).
MATCH (c:Company)-[:MAKES]->(p:Product)
RETURN coalesce(c.name, c.id) AS maker, count(DISTINCT p) AS products
ORDER BY products DESC, maker LIMIT 10;

// 3. most common active ingredients.
MATCH (p:Product)-[:CONTAINS]->(part:Part)
RETURN coalesce(part.name, part.id) AS ingredient, count(DISTINCT p) AS products
ORDER BY products DESC, ingredient LIMIT 10;

// 4. drugs sharing an ingredient with a given drug (by product id).
MATCH (p:Product {id: $ndc})-[:CONTAINS]->(part:Part)<-[:CONTAINS]-(other:Product)
WHERE other <> p
RETURN part.name AS shared_ingredient, collect(DISTINCT other.name) AS also_in;

// 5. makes relationships filtered by confidence (original packagers only).
MATCH (c:Company)-[r:MAKES]->(p:Product)
WHERE r.confidence >= 0.9
RETURN c.name AS maker, p.name AS product, r.confidence, r.source_record
ORDER BY maker LIMIT 25;

// 6. shortest path between two companies through shared ingredients.
MATCH (a:Company {id: $co_a}), (b:Company {id: $co_b}),
      path = shortestPath((a)-[:MAKES|CONTAINS*]-(b))
RETURN [n IN nodes(path) | coalesce(n.name, n.id)] AS hops, length(path) AS len;
