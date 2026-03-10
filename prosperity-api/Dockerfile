# Stage 1: Build
FROM eclipse-temurin:21-jdk AS build
WORKDIR /app
COPY pom.xml .
COPY mvnw .
COPY .mvn .mvn
RUN chmod +x mvnw && ./mvnw dependency:go-offline -q
COPY src ./src
RUN ./mvnw package -DskipTests -q

# Stage 2: Run
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
RUN useradd -r -s /bin/false app
EXPOSE 8080
USER app
ENTRYPOINT ["java", "-jar", "app.jar"]
