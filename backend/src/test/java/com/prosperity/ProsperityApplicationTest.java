package com.prosperity;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.SpringBootApplication;

class ProsperityApplicationTest {

  @Test
  void applicationHasSpringBootAnnotation() {
    assertThat(ProsperityApplication.class.getAnnotation(SpringBootApplication.class)).isNotNull();
  }
}
