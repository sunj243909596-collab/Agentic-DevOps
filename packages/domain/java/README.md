# Java Domain Models

The Java model is dependency-free and uses Java records and enums.

Entry point:

```java
import com.devmanager.domain.DomainModels.AnalysisRun;
import com.devmanager.domain.DomainModels.RunStatus;
```

The records use idiomatic camelCase field names. API serialization can map them to snake_case using the chosen JSON library configuration.
