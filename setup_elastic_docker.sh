#!/bin/bash
# setup_elastic_docker.sh
# Setup Elasticsearch + Kibana dengan SSL di Docker

set -e

echo "=============================================="
echo "   AquaGuard Elasticsearch Setup (Docker)"
echo "=============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ==================== CONFIG ====================
ELASTIC_PASSWORD="3+xHEqNsZYJ*2CQoNAlG"
KIBANA_PASSWORD="$ELASTIC_PASSWORD"

CERT_VOLUME="projek_sistemoperasi_certs"
ES_VOLUME="projek_sistemoperasi_esdata"

# ==================== STEP 1: Cleanup Old Containers ====================
echo -e "\n${YELLOW}[1/6] Cleaning up old containers...${NC}"
docker-compose down -v 2>/dev/null || true
docker volume rm -f ${ES_VOLUME} ${CERT_VOLUME} 2>/dev/null || true
echo -e "${GREEN}✓ Cleanup complete.${NC}"

# ==================== STEP 2: Create Volumes ====================
echo -e "\n${YELLOW}[2/6] Creating Docker volumes...${NC}"
docker volume create ${CERT_VOLUME}
docker volume create ${ES_VOLUME}
echo -e "${GREEN}✓ Volumes created: ${ES_VOLUME}, ${CERT_VOLUME}${NC}"

# ==================== STEP 3: Generate Certificates ====================
echo -e "\n${YELLOW}[3/6] Generating SSL certificates (this may take a moment)...${NC}"

# [SIMPLIFIED] Gunakan elasticsearch-certutil untuk generate PKCS12 langsung
docker run --rm --user root \
  -v ${CERT_VOLUME}:/usr/share/elasticsearch/config/certs \
  elasticsearch:8.11.0 \
  bash -c '
    # Setup direktori dengan permission yang benar
    mkdir -p /usr/share/elasticsearch/config/certs
    chown -R elasticsearch:elasticsearch /usr/share/elasticsearch/config/certs
    
    # Switch ke user elasticsearch untuk generate certificate
    su - elasticsearch -s /bin/bash -c "
      cd /usr/share/elasticsearch
      
      echo \"Generating CA and node certificates in one step...\";
      
      # Generate CA
      bin/elasticsearch-certutil ca \
        --out config/certs/elastic-stack-ca.p12 \
        --pass \"\";
      
      # Generate node certificate dengan CA yang baru dibuat
      bin/elasticsearch-certutil cert \
        --ca config/certs/elastic-stack-ca.p12 \
        --ca-pass \"\" \
        --name elasticsearch \
        --dns elasticsearch \
        --dns localhost \
        --ip 127.0.0.1 \
        --out config/certs/elasticsearch-certificates.p12 \
        --pass \"\";
      
      # Copy untuk HTTP dan Transport (keduanya sama)
      cp config/certs/elasticsearch-certificates.p12 config/certs/http.p12;
      cp config/certs/elasticsearch-certificates.p12 config/certs/transport.p12;
      
      # Extract CA certificate untuk Flask app (PEM format)
      bin/elasticsearch-certutil ca --pem --out /tmp/ca.zip --pass \"\";
      unzip -q /tmp/ca.zip -d config/certs;
      
      echo \"Certificates generated successfully!\";
    "
    
    # Final permission check
    chown -R elasticsearch:elasticsearch /usr/share/elasticsearch/config/certs
  '

if [ $? -eq 0 ]; then
  echo -e "${GREEN}✓ Certificates created in volume '${CERT_VOLUME}'${NC}"
else
  echo -e "${RED}✗ Certificate generation failed${NC}"
  exit 1
fi

# ==================== STEP 4: Start Services ====================
echo -e "\n${YELLOW}[4/6] Starting Elasticsearch and Kibana... (This will take 2-3 minutes)${NC}"
docker-compose up -d

# Wait for Elasticsearch
echo -e "\n${YELLOW}Waiting for Elasticsearch to be healthy...${NC}"
MAX_WAIT=300 # 5 menit
COUNTER=0
until [ "$(docker inspect -f '{{.State.Health.Status}}' elasticsearch 2>/dev/null)" == "healthy" ]; do
  echo -n "."
  sleep 5
  COUNTER=$((COUNTER + 5))
  if [ $COUNTER -ge $MAX_WAIT ]; then
    echo -e "\n${RED}✗ Elasticsearch failed to start within ${MAX_WAIT} seconds${NC}"
    echo -e "${YELLOW}Checking logs:${NC}"
    docker logs elasticsearch --tail 50
    exit 1
  fi
done
echo -e "\n${GREEN}✓ Elasticsearch is ready!${NC}"

# ==================== STEP 5: Extract CA Certificate ====================
echo -e "\n${YELLOW}[5/6] Extracting CA certificate for Flask app...${NC}"

# Sekarang extract dari container yang sudah running
docker cp elasticsearch:/usr/share/elasticsearch/config/certs/ca/ca.crt ./http_ca.crt

if [ -f "http_ca.crt" ]; then
  chmod 644 http_ca.crt
  echo -e "${GREEN}✓ CA certificate saved: $(pwd)/http_ca.crt${NC}"
else
  echo -e "${RED}✗ Failed to extract CA certificate${NC}"
  exit 1
fi

# ==================== STEP 6: Setup Kibana System User ====================
echo -e "\n${YELLOW}[6/6] Setting up Kibana system user password...${NC}"

docker exec elasticsearch curl -k -X POST \
  -u "elastic:$ELASTIC_PASSWORD" \
  "https://localhost:9200/_security/user/kibana_system/_password" \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"$KIBANA_PASSWORD\"}" \
  2>/dev/null || true

echo -e "${GREEN}✓ Kibana system password set.${NC}"

# Restart Kibana
echo -e "\n${YELLOW}Restarting Kibana...${NC}"
docker-compose restart kibana

# Wait for Kibana
echo -e "\n${YELLOW}Waiting for Kibana to be healthy...${NC}"
COUNTER=0
until [ "$(docker inspect -f '{{.State.Health.Status}}' kibana 2>/dev/null)" == "healthy" ]; do
  echo -n "."
  sleep 5
  COUNTER=$((COUNTER + 5))
  if [ $COUNTER -ge $MAX_WAIT ]; then
    echo -e "\n${YELLOW}Kibana taking longer than expected. Check logs:${NC}"
    echo -e "${YELLOW}docker logs kibana${NC}"
    break
  fi
done

echo -e "\n${GREEN}✓ Kibana is ready!${NC}"

# ==================== SUMMARY ====================
echo -e "\n=============================================="
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "==============================================\n"

echo -e "${YELLOW}Access URLs:${NC}"
echo -e "   Elasticsearch: ${GREEN}https://localhost:9200${NC}"
echo -e "   Kibana:        ${GREEN}http://localhost:5601${NC}"

echo -e "\n${YELLOW}Credentials:${NC}"
echo -e "   Username: ${GREEN}elastic${NC}"
echo -e "   Password: ${GREEN}$ELASTIC_PASSWORD${NC}"

echo -e "\n${YELLOW}CA Certificate:${NC}"
echo -e "   Location: ${GREEN}$(pwd)/http_ca.crt${NC}"
echo -e "   (Gunakan file ini di server_middleware_final.py-mu!)"

echo -e "\n${YELLOW}Verify Setup:${NC}"
echo -e "   Test Elasticsearch: ${GREEN}curl -k -u elastic:$ELASTIC_PASSWORD https://localhost:9200${NC}"
echo -e "   Check logs: ${GREEN}docker logs elasticsearch${NC}"

echo ""