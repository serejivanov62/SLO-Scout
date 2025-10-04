FROM openjdk:11-jdk-slim AS builder

WORKDIR /build

# Copy Gradle files
COPY build.gradle settings.gradle gradlew ./
COPY gradle ./gradle

# Download dependencies
RUN ./gradlew dependencies --no-daemon

# Copy source code
COPY src ./src

# Build the application
RUN ./gradlew shadowJar --no-daemon

# Runtime image
FROM openjdk:11-jre-slim

WORKDIR /app

# Copy the fat JAR
COPY --from=builder /build/build/libs/*.jar ./app.jar

# Create non-root user
RUN useradd -r -u 1000 flink
USER flink

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD test -f /tmp/flink-health || exit 1

# Run the Flink job
ENTRYPOINT ["java", "-jar", "app.jar"]
