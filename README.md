# Seguridad en NoSQL: FastAPI, MongoDB y Elasticsearch

Laboratorio de seguridad desarrollado con Docker Compose. Se parte de una configuración deliberadamente vulnerable y se aplican validación de entradas, autenticación, reducción de exposición, TLS, limitación de frecuencia, registros, alertas y copia lógica de MongoDB.

> Uso exclusivamente educativo, sobre sistemas propios y datos de prueba. La configuración inicial vulnerable no debe publicarse en Internet ni ejecutarse en una red no controlada.

## 1. Alcance y estado del repositorio

Este README documenta los pasos seguidos y las pruebas del laboratorio. No es un instalador automático ni sustituye los archivos de implementación.

- MongoDB: imagen `mongo:7`.
- Elasticsearch: `docker.elastic.co/elasticsearch/elasticsearch:7.17.10`.
- FastAPI: imagen construida desde `python:3.11-slim` y servida con Uvicorn.
- Las versiones anteriores corresponden al laboratorio; no constituyen una recomendación de versiones para producción.
- Los endpoints utilizados son `/login_mongo`, `/articulos` y los de pedidos que implemente `main.py`.
- No se incluyen aquí contraseñas reales. Las variables y los comandos deben ajustarse al Compose final.

### Precaución sobre los datos

Antes de recrear MongoDB o Elasticsearch, comprobar los montajes de datos. Los montajes de certificados **no** proporcionan persistencia a las colecciones ni a los índices. Una nueva ejecución con datos vacíos puede requerir inicialización o restauración.

No utilizar `docker compose down -v` para reiniciar: puede eliminar volúmenes y datos. No sobrescribir la configuración endurecida con la vulnerable para repetir capturas.

## 2. Arquitectura final

```text
Cliente / curl
    |
    | HTTPS :8000 — certificado autofirmado api.crt
    v
FastAPI / Uvicorn
    |-- TLS --> mongo:27017
    |             CA: ca.crt; cuenta: app_user
    |
    `-- HTTPS --> elasticsearch:9200
                  CA: ca.crt; cuenta utilizada en el laboratorio: elastic
```

- Solo se publica el puerto 8000 en el host en el Compose trabajado.
- MongoDB y Elasticsearch se consultan desde la red interna de Docker.
- No hay sincronización automática MongoDB–Elasticsearch.
- Uvicorn termina HTTPS directamente: no se necesita Nginx para esta práctica.
- Se configura HTTPS en la API HTTP de Elasticsearch (9200); no se documenta TLS de transporte entre nodos en 9300.
- La cuenta `elastic` debe sustituirse por una cuenta restringida para un despliegue de mayor alcance.

## 3. Estructura prevista

```text
.
├── docker-compose.yml
├── init_mongo.js
├── init_elastic.sh              # comprobar el nombre real del script
├── fastapi-app/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── certs/                      # material generado localmente
│   ├── api.crt
│   ├── api.key
│   ├── mongo/
│   │   ├── ca.crt
│   │   ├── ca.key
│   │   ├── mongo.crt
│   │   └── mongo.pem
│   └── elastic/
│       ├── elastic.crt
│       └── elastic.key
├── backups/                    # copias locales, fuera de Git
└── README.md
```

Las solicitudes CSR, archivos de extensiones y seriales también se generan durante la firma. Su omisión en el árbol es únicamente para facilitar la lectura.

## 4. Requisitos

- Docker Engine o Docker Desktop con el complemento Docker Compose.
- Terminal compatible con los ejemplos Bash.
- OpenSSL y curl en el equipo anfitrión.
- Git, para conservar las fases y versiones del trabajo.

Desde la raíz del proyecto:

```bash
docker --version
docker compose version
openssl version
curl --version
```

## 5. Fase inicial: infraestructura vulnerable

La fase de referencia utilizó MongoDB sin exigir autenticación, Elasticsearch con `xpack.security.enabled: "false"`, puertos de datos publicados y comunicaciones sin TLS.

Se levantaron los servicios y se comprobaron los endpoints funcionales:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail 50
```

> Estos comandos usan la configuración que esté guardada actualmente. No generan por sí solos el baseline vulnerable. Para repetir esta fase, utilizar una revisión o un Compose de laboratorio separado, si se ha conservado.

En el baseline se verificaron los puertos, la ausencia de TLS y autenticación y los registros disponibles. Las pruebas se documentan en la memoria con evidencia antes/después.

### 5.1 Inyección NoSQL en login

Payload de prueba sobre el baseline aislado:

```bash
curl -i -X POST 'http://localhost:8000/login_mongo' \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":{"$ne":"x"}}'
```

La prueba introduce un objeto en lugar de una contraseña literal. El resultado depende de los datos de prueba y del código vulnerable. Tras endurecer, el mismo objeto debe rechazarse por validación, no utilizarse como condición de MongoDB.

### 5.2 Acceso anónimo a motores

Se ensayaron lectura y escritura sobre datos desechables de MongoDB y enumeración/búsqueda sin credenciales en Elasticsearch. Deben conservarse los comandos y resultados originales en la memoria.

Ejemplos de lectura del baseline:

```bash
curl -i 'http://localhost:9200/_cat/indices?v'
curl -i 'http://localhost:9200/articulos/_search?q=*'
```

La prueba destructiva exigida por la actividad se limita a un índice desechable. No se proporciona un comando de borrado de `articulos` en esta guía de operación final para evitar eliminar el dataset funcional por error.

## 6. Defensa mínima aplicada

### 6.1 Reducir exposición

Se retiraron las publicaciones de puertos 27017 y 9200 del Compose. Esto reduce la exposición en el host, pero no impide todos los accesos entre contenedores de una red compartida.

### 6.2 Validar entradas

En `main.py` se incorporaron:

- Modelo Pydantic para usuario y contraseña de tipo texto.
- Restricciones de longitud y validadores adicionales.
- Rechazo del carácter `$` conforme a las reglas del laboratorio.
- Consultas de estructura fijada en el servidor, con valores validados.

La defensa principal frente al objeto `$ne` es impedir que el cliente introduzca estructura de consulta en un campo literal. Bloquear un carácter no sustituye esta protección.

### 6.3 Autenticación de MongoDB

Se activó `--auth`, se creó `app_user` y se configuró FastAPI con `MONGO_USER`, `MONGO_PASS` y la base de autenticación `tienda`.

Los documentos de la colección `usuarios` son usuarios funcionales de la aplicación; no equivalen a cuentas del motor. El rol de `app_user` debe verificarse en el script final y limitarse al ámbito necesario.

`init_mongo.js` no debe darse por reaplicado al reiniciar una base ya inicializada. Si faltan cuentas en una instalación existente, resolver su creación con una identidad administrativa autorizada; no borrar datos para forzar el script.

### 6.4 Autenticación de Elasticsearch y búsqueda controlada

Se activó la seguridad y se configuraron credenciales para las llamadas desde FastAPI. Se sustituyó el paso directo de `q` a la sintaxis de búsqueda por una consulta `match` sobre `titulo` y se añadieron límites de paginación.

`match` es búsqueda de texto analizado, no coincidencia exacta. La paginación limita respuestas, pero no evita por sí sola recorrer datos mediante varias solicitudes.

## 7. Generación de certificados TLS

> Ejecutar solo en una instalación nueva. No sobrescribir certificados o claves existentes sin planificar su renovación. Generar todos los archivos antes de activar sus bind mounts: Docker puede crear directorios si el origen de un montaje corto no existe.

### 7.1 Certificado del frontal

Desde la raíz:

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout certs/api.key \
  -out certs/api.crt \
  -days 365 \
  -subj '/CN=localhost' \
  -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'
```

Este certificado es autofirmado y se utiliza únicamente para el frontal. El cliente confía explícitamente en él mediante `--cacert`.

### 7.2 CA local

La carpeta `certs/mongo` es una ubicación del proyecto; la CA puede firmar certificados de ambos motores.

```bash
mkdir -p certs/mongo certs/elastic
openssl req -x509 -newkey rsa:2048 -nodes -sha256 \
  -keyout certs/mongo/ca.key \
  -out certs/mongo/ca.crt \
  -days 365 \
  -subj '/CN=CA-Laboratorio-Mongo' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign'
```

La clave `ca.key` se utiliza para firmar; no se monta en FastAPI ni en las bases de datos. Los ejemplos generan claves sin contraseña para permitir el arranque desatendido del laboratorio; deben protegerse mediante permisos y acceso al host.

### 7.3 Certificado de MongoDB

```bash
openssl req -new -newkey rsa:2048 -nodes \
  -keyout certs/mongo/mongo.key \
  -out certs/mongo/mongo.csr \
  -subj '/CN=mongo'

cat > certs/mongo/mongo.ext <<'EOF'
subjectAltName=DNS:mongo,DNS:localhost,IP:127.0.0.1
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF

openssl x509 -req \
  -in certs/mongo/mongo.csr \
  -CA certs/mongo/ca.crt -CAkey certs/mongo/ca.key \
  -CAcreateserial \
  -out certs/mongo/mongo.crt \
  -days 365 -sha256 -extfile certs/mongo/mongo.ext

cat certs/mongo/mongo.key certs/mongo/mongo.crt \
  > certs/mongo/mongo.pem

openssl verify -CAfile certs/mongo/ca.crt certs/mongo/mongo.crt
```

### 7.4 Certificado de Elasticsearch

```bash
openssl req -new -newkey rsa:2048 -nodes \
  -keyout certs/elastic/elastic.key \
  -out certs/elastic/elastic.csr \
  -subj '/CN=elasticsearch'

cat > certs/elastic/elastic.ext <<'EOF'
subjectAltName=DNS:elasticsearch,DNS:localhost,IP:127.0.0.1
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF

openssl x509 -req \
  -in certs/elastic/elastic.csr \
  -CA certs/mongo/ca.crt -CAkey certs/mongo/ca.key \
  -CAcreateserial \
  -out certs/elastic/elastic.crt \
  -days 365 -sha256 -extfile certs/elastic/elastic.ext

openssl verify -CAfile certs/mongo/ca.crt certs/elastic/elastic.crt
```

Ambas verificaciones deben devolver `OK`. Esto valida los archivos; las pruebas de conexión de la sección 10 validan el uso real de TLS.

## 8. Activación de TLS

### 8.1 Uvicorn y montajes de FastAPI

CMD final del Dockerfile:

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--ssl-keyfile", "/certs/api.key", "--ssl-certfile", "/certs/api.crt"]
```

Montajes dentro de `fastapi-app` en Compose:

```yaml
volumes:
  - ./certs/api.key:/certs/api.key:ro
  - ./certs/api.crt:/certs/api.crt:ro
  - ./certs/mongo/ca.crt:/mongo-certs/ca.crt:ro
```

La parte izquierda es la ruta del host; la derecha es la ruta que debe utilizar Python. No copiar claves privadas a la imagen ni montar toda la carpeta de certificados en FastAPI.

### 8.2 MongoDB

Opciones añadidas a `command`:

```yaml
command:
  - '--auth'
  - '--tlsMode'
  - 'requireTLS'
  - '--tlsCertificateKeyFile'
  - '/certs/mongo.pem'
  - '--tlsCAFile'
  - '/certs/ca.crt'
  - '--tlsAllowConnectionsWithoutCertificates'
```

Montajes, conservando los scripts y volúmenes de datos que ya existan:

```yaml
volumes:
  - ./certs/mongo/mongo.pem:/certs/mongo.pem:ro
  - ./certs/mongo/ca.crt:/certs/ca.crt:ro
```

La última opción permite clientes sin certificado propio: la autenticación del cliente sigue realizándose mediante cuenta y contraseña. No elimina el requisito de TLS ni activa mTLS.

Añadir a la conexión MongoClient existente sin cambiar innecesariamente el nombre de la variable utilizada por el resto del código:

```python
tls=True,
tlsCAFile="/mongo-certs/ca.crt",
```

### 8.3 Elasticsearch

Añadir al `environment` existente:

```yaml
xpack.security.http.ssl.enabled: 'true'
xpack.security.http.ssl.key: certs/elastic.key
xpack.security.http.ssl.certificate: certs/elastic.crt
```

Montajes:

```yaml
volumes:
  - ./certs/elastic/elastic.key:/usr/share/elasticsearch/config/certs/elastic.key:ro
  - ./certs/elastic/elastic.crt:/usr/share/elasticsearch/config/certs/elastic.crt:ro
  - ./certs/mongo/ca.crt:/usr/share/elasticsearch/config/certs/ca.crt:ro
```

FastAPI utiliza la URL `https://elasticsearch:9200/articulos/_search`, credenciales y:

```python
verify="/mongo-certs/ca.crt",
timeout=10,
```

No utilizar `verify=False` ni desactivar la comprobación del nombre del servidor.

### 8.4 Aplicar cambios

Tras confirmar los volúmenes de datos y la existencia de los certificados:

```bash
docker compose config --quiet
docker compose up -d --build mongo elasticsearch fastapi-app
docker compose ps
docker compose logs --tail 50 fastapi-app
```

Si las claves no son legibles por el usuario del proceso, revisar propietario, grupo y permisos de forma específica. No resolverlo haciendo públicas todas las claves con permisos indiscriminados.

## 9. Carga de artículos tras activar HTTPS

Si el índice está vacío o no existe, ejecutar la carga desde el contenedor; no es necesario publicar 9200.

> Se utiliza `ELASTIC_PASSWORD` tal como está configurada en el contenedor del laboratorio. Comprobar que corresponda a la contraseña vigente de la cuenta. Los IDs 1, 2 y 3 se crean o reemplazan.

```bash
docker compose exec -T elasticsearch sh -c '
  curl -sS \
    --cacert /usr/share/elasticsearch/config/certs/ca.crt \
    -u "elastic:$ELASTIC_PASSWORD" \
    -X POST "https://localhost:9200/_bulk?refresh=true&pretty" \
    -H "Content-Type: application/x-ndjson" \
    --data-binary @-
' <<'EOF'
{ "index": { "_index": "articulos", "_id": "1" } }
{ "titulo": "Teclado mecánico", "categoria": "periféricos", "precio": 59.90 }
{ "index": { "_index": "articulos", "_id": "2" } }
{ "titulo": "Ratón inalámbrico", "categoria": "periféricos", "precio": 24.50 }
{ "index": { "_index": "articulos", "_id": "3" } }
{ "titulo": "Monitor 27 pulgadas", "categoria": "pantallas", "precio": 189.00 }
EOF
```

Comprobar `"errors": false`: HTTP 200 no garantiza que todas las operaciones bulk hayan tenido éxito. El script `init_elastic.sh` debe adaptarse a este mismo acceso HTTPS y ejecutarse cuando Elasticsearch esté preparado; un archivo .sh no se ejecuta automáticamente por estar en el repositorio.

## 10. Verificación final

Los resultados siguientes son los **esperados**. Guardar las salidas reales como evidencias; la presencia del comando no acredita su ejecución.

### 10.1 Cliente → API → Elasticsearch

```bash
curl --cacert certs/api.crt -i \
  'https://localhost:8000/articulos?q=teclado'
```

Esperado: HTTP 200 y el teclado. Utilizar siempre HTTPS en los endpoints tras el cambio; no se ha configurado redirección de HTTP.

### 10.2 MongoDB con TLS

```bash
docker compose exec mongo mongosh \
  'mongodb://localhost:27017/tienda?directConnection=true&serverSelectionTimeoutMS=5000' \
  --tls --tlsCAFile /certs/ca.crt \
  --eval 'db.runCommand({ping:1})'
```

Esperado: `{ ok: 1 }`. Se usa ping para separar transporte y permiso de lectura.

### 10.3 MongoDB sin TLS

```bash
docker compose exec mongo mongosh \
  'mongodb://localhost:27017/tienda?directConnection=true&serverSelectionTimeoutMS=5000&tls=false' \
  --eval 'db.runCommand({ping:1})'
```

Esperado: fallo o cierre de conexión, no un ping correcto.

### 10.4 MongoDB sin credenciales y con TLS

```bash
docker compose exec mongo mongosh \
  --host localhost --tls --tlsCAFile /certs/ca.crt \
  tienda --eval 'db.usuarios.countDocuments({})'
```

Esperado: error de autorización. Esta prueba valida el control de acceso, no el rechazo de tráfico sin cifrar.

### 10.5 MongoDB autenticado

```bash
docker compose exec mongo mongosh \
  --host localhost --tls --tlsCAFile /certs/ca.crt \
  --username app_user --authenticationDatabase tienda \
  tienda --eval 'db.usuarios.countDocuments({})' --password
```

Introducir la contraseña de la cuenta. Esperado: `3` si se conservan los tres usuarios del dataset del laboratorio.

### 10.6 Elasticsearch con HTTPS y autenticación

```bash
docker compose exec elasticsearch curl -v \
  --cacert /usr/share/elasticsearch/config/certs/ca.crt \
  -u elastic 'https://localhost:9200/articulos/_count?pretty'
```

Introducir la contraseña cuando se solicite. Esperado: verificación TLS correcta, HTTP 200 y `"count": 3` si solo están los artículos del ejemplo. No compartir logs verbosos sin revisar si contienen cabeceras o secretos.

### 10.7 Elasticsearch sin TLS

```bash
docker compose exec elasticsearch curl -v --max-time 5 \
  'http://localhost:9200/'

docker compose logs --since 2m elasticsearch \
  | grep -i 'plaintext http traffic'
```

Esperado: cierre de conexión o respuesta vacía y aviso `received plaintext http traffic on an https channel`. No se envían credenciales por HTTP.

### 10.8 Elasticsearch sin autenticación

```bash
docker compose exec elasticsearch curl -i \
  --cacert /usr/share/elasticsearch/config/certs/ca.crt \
  'https://localhost:9200/_cat/indices?v'
```

Esperado: HTTP 401 con mensaje de credenciales ausentes.

### 10.9 Repetir NoSQLi tras el endurecimiento

```bash
curl --cacert certs/api.crt -i \
  -X POST 'https://localhost:8000/login_mongo' \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":{"$ne":"x"}}'
```

Esperado: rechazo de validación, normalmente HTTP 422 con el modelo utilizado. Si devuelve 429, esperar a que termine la ventana de rate limit antes de repetir el caso.

## 11. Rate limit y alertas

Se añadió SlowAPI a `requirements.txt` y se configuraron el limitador, los decoradores y el manejador de `RateLimitExceeded`.

Política acordada durante la práctica:

- Login: 5 solicitudes/minuto.
- Búsqueda: 30 solicitudes/minuto.

Verificar que el código final mantiene estos valores. El manejador personaliza respuesta y log; no sustituye al limitador.

Tras un minuto sin peticiones desde la misma clave de cliente:

```bash
for i in $(seq 1 32); do
  curl --cacert certs/api.crt -sS -o /dev/null \
    -w '%{http_code} ' \
    'https://localhost:8000/articulos?q=teclado'
done
echo
```

Esperado: respuestas 200 y posteriormente 429 al superar el límite efectivo. Peticiones previas o una IP compartida pueden cambiar el punto del bloqueo.

Se añadieron alertas de login fallido y picos de búsqueda mediante ventanas temporales. Consultar el código final para confirmar umbrales y duración: durante la documentación aparecieron referencias contradictorias a 60 segundos y 30 minutos, que deben unificarse antes de presentar resultados.

```bash
docker compose logs --since 5m fastapi-app \
  | grep -Ei 'ALERTA|rate limit|ratelimit|login'
```

La alerta registrada en logs no equivale a notificación externa ni a respuesta automática. Documentar si los contadores son en memoria y sus límites ante reinicios o varias réplicas.

## 12. Copia lógica de MongoDB

La copia con `mongodump` es una copia lógica, no un snapshot de volumen. El comando debe usar TLS una vez activado `requireTLS`.

Ejemplo que pide la contraseña en una variable temporal de Bash y comprueba el resultado antes de renombrar el archivo. No usa la entrada estándar de `mongodump`, reservada al proceso de Docker:

```bash
mkdir -p backups
read -r -s -p 'Contraseña de app_user: ' MONGO_BACKUP_PASS
echo
archive="backups/tienda-$(date +%Y%m%d-%H%M%S).archive"

if docker compose exec -T -e MONGO_BACKUP_PASS="$MONGO_BACKUP_PASS" mongo sh -c '
  mongodump --host localhost \
    --username app_user --password "$MONGO_BACKUP_PASS" \
    --authenticationDatabase tienda --db tienda \
    --ssl --sslCAFile /certs/ca.crt --archive
' > "${archive}.partial"; then
  if [ -s "${archive}.partial" ]; then
    mv "${archive}.partial" "$archive"
    ls -lh "$archive"
  else
    echo 'ERROR: archivo vacío; no considerar la copia válida.' >&2
  fi
else
  echo 'ERROR: mongodump falló; revisar el archivo parcial y el mensaje.' >&2
fi
unset MONGO_BACKUP_PASS
```

Las herramientas de base de datos emplean las opciones `--ssl`/`--sslCAFile`; comprobar `mongodump --help` en la imagen utilizada. La contraseña temporal sigue siendo accesible a procesos con privilegios suficientes: este ejemplo es para el laboratorio.

Verificar que la cuenta tiene los permisos necesarios para el alcance del dump; no conceder permisos administrativos generales para resolver un error. Una copia válida requiere además probar la restauración en un entorno aislado. No restaurar sobre datos de trabajo sin plan de recuperación.