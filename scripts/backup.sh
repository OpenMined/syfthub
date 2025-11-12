#!/bin/sh
# Database backup script for production

set -e

# Configuration
BACKUP_DIR="/backup"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/syfthub_backup_${TIMESTAMP}.sql"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

echo "Starting database backup at ${TIMESTAMP}"

# Create backup directory if it doesn't exist
mkdir -p ${BACKUP_DIR}

# Perform backup based on database type
if [ -n "$POSTGRES_HOST" ]; then
    # PostgreSQL backup
    echo "Backing up PostgreSQL database..."
    PGPASSWORD=$POSTGRES_PASSWORD pg_dump \
        -h $POSTGRES_HOST \
        -U $POSTGRES_USER \
        -d $POSTGRES_DB \
        -f ${BACKUP_FILE} \
        --verbose \
        --no-owner \
        --no-acl

elif [ -n "$MYSQL_HOST" ]; then
    # MySQL backup
    echo "Backing up MySQL database..."
    mysqldump \
        -h $MYSQL_HOST \
        -u $MYSQL_USER \
        -p$MYSQL_PASSWORD \
        $MYSQL_DATABASE \
        > ${BACKUP_FILE}
else
    echo "No database configuration found for backup"
    exit 1
fi

# Compress the backup
if [ -f "${BACKUP_FILE}" ]; then
    echo "Compressing backup..."
    gzip ${BACKUP_FILE}
    BACKUP_FILE="${BACKUP_FILE}.gz"
    echo "Backup saved to ${BACKUP_FILE}"

    # Calculate and display backup size
    BACKUP_SIZE=$(du -h ${BACKUP_FILE} | cut -f1)
    echo "Backup size: ${BACKUP_SIZE}"
fi

# Remove old backups
if [ $RETENTION_DAYS -gt 0 ]; then
    echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
    find ${BACKUP_DIR} -name "syfthub_backup_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
fi

# Optional: Upload to cloud storage
if [ -n "$S3_BUCKET" ]; then
    echo "Uploading backup to S3..."
    aws s3 cp ${BACKUP_FILE} s3://${S3_BUCKET}/backups/ --storage-class ${S3_STORAGE_CLASS:-STANDARD_IA}
fi

if [ -n "$GCS_BUCKET" ]; then
    echo "Uploading backup to Google Cloud Storage..."
    gsutil cp ${BACKUP_FILE} gs://${GCS_BUCKET}/backups/
fi

if [ -n "$AZURE_CONTAINER" ]; then
    echo "Uploading backup to Azure Blob Storage..."
    az storage blob upload \
        --container-name ${AZURE_CONTAINER} \
        --file ${BACKUP_FILE} \
        --name backups/$(basename ${BACKUP_FILE})
fi

echo "Backup completed successfully"
